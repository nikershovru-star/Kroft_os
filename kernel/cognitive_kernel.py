"""Cognitive Kernel — FSM implementation + reference in-memory port implementations.

K1-compliant: imports ONLY contracts + stdlib. No service/adapter/runtime imports.
Implements the Cognitive FSM (ADR-054 I-01): Idle->Observe->Orient->Deliberate->
Commit->Execute->Evaluate->Learn, with Executive as sole transition controller (I-02),
dual-process system-1 (LLM-free) / system-2 (deliberative) (I-09/I-16), and
CognitiveEvent emission on every transition (I-17).

Reference implementations (Deterministic*) are deterministic (LLM-free core) and
intended for tests + local-first operation. Production adapters (LLM-backed) plug
in via the ports in contracts.i_cognitive_kernel without touching this module.
"""

from __future__ import annotations

import uuid
import json
import re
import math
from typing import Callable, Dict, List, Optional

from contracts.cognitive_domain import (
    Action,
    CausalMark,
    CognitiveEvent,
    CognitiveEventType,
    CognitiveState,
    ConfidenceScore,
    Decision,
    Episode,
    ExecutionOutcome,
    Goal,
    Intent,
    NodeLamportClock,
    Observation,
    Plan,
    Policy,
    PolicyLifecycle,
    Provenance,
    ProvenanceType,
    SemanticFact,
    WorldState,
)
from contracts.i_cognitive_kernel import (
    ICognitiveKernel,
    IDecisionEngine,
    IExecutive,
    ILearningPolicy,
    IResourceManager,
    IValueSystem,
    IWorldState,
    IAttention,
    IReasoningEngine,
    ILayeredMemory,
)
from contracts.i_world_model import IWorldModel
from contracts.i_planner import IPlanner
from contracts.i_memory_evolution import IMemoryEvolution
from contracts.i_reflection import IReflectionEngine
from kernel.reasoning import ReferenceReasoningEngine
from kernel.world_model import ReferenceWorldModel
from kernel.planning import ReferencePlanner
from kernel.memory_evolution import ReferenceMemoryEvolution
from kernel.memory_store import InMemoryLayeredMemory
from kernel.reflection import ReferenceReflectionEngine
from kernel.runtime_reflection import (
    ReferenceRuntimeReflection,
    ReferenceTuningApplier,
)
from kernel.kernel_config import KernelConfig
from kernel.runtime_supervisor import RuntimeSupervisor
from kernel.observability import LiveMetricsCollector, LiveRuntimeMetrics
from contracts.i_observability import (
    ILiveMetricsCollector,
    METRIC_EXECUTION_SUCCESS_RATE,
    METRIC_FEDERATION_DELIVERY_SUCCESS_RATE,
    METRIC_LLM_FALLBACK_RATE,
    METRIC_MEMORY_CONSOLIDATION_CONFIDENCE,
    METRIC_MEMORY_GROWTH_RATE_PER_TICK,
)
from contracts.i_runtime_reflection import IRuntimeMetrics, RuntimeMetric
from kernel.self_evolution import (
    MemorySoftPolicySource,
    PolicyAwareValueSystem,
    KnowledgeAwareReasoning,
)
from kernel.llm_advisor import (
    LLMAdvisorReasoning,
    LLMAdvisorPlanner,
)
from contracts.i_llm_advisor import ILLMAdvisor, adapter_for
from contracts.i_self_evolution import ISoftPolicySource
from contracts import IEmbedding


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------
# Reference in-memory implementations (deterministic, LLM-free)
# --------------------------------------------------------------------------
class InMemoryWorldState(IWorldState):
    """Local node SSOT (I-07)."""

    def __init__(self, node_id: str = "local", clock: Optional["NodeLamportClock"] = None) -> None:
        self._node_id = node_id
        self._facts: Dict[str, str] = {}
        self._facts_meta: Dict[str, CausalMark] = {}
        # ТЗ-RE-01 flag 1: use the SHARED node Lamport clock. If none is injected,
        # create one (so existing callers keep working) — but the kernel always
        # passes its single clock so kernel + world share one causal order.
        self._clock = clock if clock is not None else NodeLamportClock(node_id)

    def update(self, observation: Observation, causal: Optional[CausalMark] = None) -> WorldState:
        # Advance the SHARED node Lamport clock. If a causal mark was supplied
        # (federation receive), fold it in via `receive` — this is the Lamport
        # receive-rule that makes concurrent distant writes merge causally.
        # NOTE: the node's OWN clock advances, but the stored fact mark PRESERVES
        # the original (remote) origin so future merges compare logical time, not
        # node B's counter — this keeps replicas convergent (ТЗ-CAUSAL-01).
        if causal is not None:
            self._clock.receive(causal)
            mark = causal
        else:
            mark = self._clock.tick()
        self._facts[observation.id] = observation.content
        self._facts_meta[observation.id] = mark
        return self.snapshot()

    def snapshot(self) -> WorldState:
        return WorldState(node_id=self._node_id, facts=dict(self._facts),
                          facts_meta=dict(self._facts_meta))

    def get(self, key: str) -> Optional[str]:
        return self._facts.get(key)

    def apply_remote(self, remote: "WorldState") -> WorldState:
        """ТЗ-NW-01: fold a federated (already causally-merged) WorldState into the
        local SSOT. Causal merge by CausalMark (greater wins); local clock advanced
        via the Lamport receive-rule so future comparisons use logical time. Idempotent
        on replay of the same message.
        """
        max_remote = CausalMark(self._node_id, 0)
        for k, rm in remote.facts_meta.items():
            if rm > max_remote:
                max_remote = rm
        for k, v in remote.facts.items():
            rmark = remote.facts_meta.get(k)
            lmark = self._facts_meta.get(k)
            if rmark is not None and (lmark is None or rmark > lmark):
                self._facts[k] = v
                self._facts_meta[k] = rmark
        if max_remote.lamport > self._clock.mark.lamport:
            self._clock.receive(max_remote)
        return self.snapshot()


class SimpleResourceManager(IResourceManager):
    """Deterministic budget enforcement (I-06)."""

    def __init__(self, budgets: Optional[Dict[str, int]] = None) -> None:
        self._budgets = dict(budgets or {"tokens": 100000, "llm_calls": 1000, "agents": 16})

    def request_quota(self, requester: str, kind: str, amount: int) -> int:
        avail = self._budgets.get(kind, 0)
        granted = min(amount, avail)
        self._budgets[kind] = avail - granted
        return granted

    def remaining(self, kind: str) -> int:
        return self._budgets.get(kind, 0)


class SimpleAttention(IAttention):
    """Cognitive selector (I-05). NOT a resource manager — queries ResourceManager."""

    def __init__(self, resources: IResourceManager) -> None:
        self._res = resources

    def select_context(self, intent: Intent, world: WorldState,
                       budget_tokens: int) -> List[str]:
        # deterministic: pick facts by token budget, cap by granted quota
        granted = self._res.request_quota("attention", "tokens", budget_tokens)
        items = list(world.facts.keys())
        # simple focus: most recent first (by insertion order), fit within granted/10
        cap = max(1, granted // 10)
        return items[-cap:]

    def salience(self, item_id: str, intent: Intent, world: WorldState) -> ConfidenceScore:
        # deterministic proxy: goal-relevance = token overlap with intent text
        content = world.facts.get(item_id, "")
        overlap = len(set(content.lower().split()) & set(intent.text.lower().split()))
        val = min(1.0, 0.3 + 0.1 * overlap)
        return ConfidenceScore(val, ProvenanceType.RULE_INFERENCE)


from kernel.value_system import SimpleValueSystem  # ТЗ-SE-01: extracted to break import cycle


class DeterministicDecisionEngine(IDecisionEngine):
    """Expected-utility selection, DETERMINISTIC (I-03). LLM = advisor only (not used here)."""

    def select(self, goal: Goal, candidates: List[Plan],
               values: IValueSystem, world: Optional["WorldState"] = None,
               intent: Optional["Intent"] = None) -> Decision:
        valid = [p for p in candidates if not values.hard_violations(p)]
        if not valid:
            # reject: no hard-valid candidate
            return Decision(
                id=_uid("dec"), goal_id=goal.id, selected_plan_id="",
                rationale="REJECTED: all candidates violate hard constraints",
                confidence=ConfidenceScore(0.0, ProvenanceType.RULE_INFERENCE),
                provenance=Provenance(source="decision", actor="kernel"),
            )
        # pick max soft score
        best = max(valid, key=lambda p: values.score(p))
        return Decision(
            id=_uid("dec"), goal_id=goal.id, selected_plan_id=best.id,
            rationale=f"expected-utility max (score={values.score(best):.3f})",
            confidence=best.confidence,
            provenance=Provenance(source="decision", actor="kernel"),
        )


class DeterministicExecutive(IExecutive):
    """Sole transition authority (I-02). NEVER reasons. Enforces LLM-free routing."""

    _ALLOWED = {
        CognitiveState.IDLE: {CognitiveState.OBSERVE},
        CognitiveState.OBSERVE: {CognitiveState.ORIENT, CognitiveState.IDLE},
        CognitiveState.ORIENT: {CognitiveState.DELIBERATE, CognitiveState.EXECUTE},
        CognitiveState.DELIBERATE: {CognitiveState.COMMIT, CognitiveState.ORIENT},
        CognitiveState.COMMIT: {CognitiveState.EXECUTE, CognitiveState.DELIBERATE},
        CognitiveState.EXECUTE: {CognitiveState.EVALUATE},
        CognitiveState.EVALUATE: {CognitiveState.LEARN, CognitiveState.IDLE},
        CognitiveState.LEARN: {CognitiveState.IDLE},
    }

    def __init__(self, resources: IResourceManager) -> None:
        self._res = resources
        self._interrupted = False

    def can_transition(self, frm: str, to: str) -> bool:
        if self._interrupted:
            return False
        allowed = self._ALLOWED.get(CognitiveState(frm), set())
        return CognitiveState(to) in allowed

    def interrupt(self, reason: str) -> None:
        self._interrupted = True

    def route_to_llm(self, context: str) -> bool:
        # LLM-free core: route to LLM only if token budget remains AND no rule covers
        granted = self._res.request_quota("executive", "llm_calls", 1)
        return granted > 0  # rule-coverage check would plug in here via adapter


class SimpleLearningPolicy(ILearningPolicy):
    """Learning proposes; never writes memory directly (I-14). Confidence+repetition gated."""

    def __init__(self, episode_log: Optional[List[str]] = None,
                 confidence_threshold: float = 0.7, min_repetitions: int = 2) -> None:
        self._log = episode_log if episode_log is not None else []
        self._thr = confidence_threshold
        self._min_rep = min_repetitions

    def propose(self, episode_ids: List[str]) -> Optional[Policy]:
        self._log.extend(episode_ids)
        # gate: need enough repetitions AND a high-confidence episode to make a rule
        from collections import Counter
        counts = Counter(self._log)
        top, n = counts.most_common(1)[0] if counts else ("", 0)
        if n >= self._min_rep:
            return Policy(
                id=_uid("pol"), name=f"learned:{top}", layer="soft",
                body=f"repeat pattern '{top}' observed {n}x",
                confidence=ConfidenceScore(min(1.0, 0.5 + 0.1 * n),
                                          ProvenanceType.AGGREGATION),
                provenance=Provenance(source="learning", actor="kernel"),
            )
        return None

    def accepts(self, proposal: Policy) -> bool:
        # Policy Check gate before Commit (I-14)
        return proposal.confidence.value >= self._thr and proposal.layer in ("soft", "hard")


# --------------------------------------------------------------------------
# Cognitive Kernel FSM (I-01)
# --------------------------------------------------------------------------
class CognitiveKernel(ICognitiveKernel):
    """Reference Cognitive Kernel. Wires the FSM + ports. Deterministic by default."""

    def __init__(self,
                 world: IWorldState,
                 attention: IAttention,
                 resources: IResourceManager,
                 values: IValueSystem,
                 decision: IDecisionEngine,
                 executive: IExecutive,
                 learning: ILearningPolicy,
                 planner: "IPlanner",
                 clock: Optional["NodeLamportClock"] = None,
                 reason: Optional["IReasoningEngine"] = None,
                 world_model: Optional["IWorldModel"] = None,
                 memory_evolution: Optional["IMemoryEvolution"] = None,
                 memory: Optional["ILayeredMemory"] = None,
                 reflection_engine: Optional["IReflectionEngine"] = None,
                 embedding: Optional["IEmbedding"] = None) -> None:
        # ТЗ-WM-01 flag A: default clock MUST derive node_id from the world, never
        # the literal "kernel" (ТЗ-RE-01 already wired node_origin=node_id when a
        # clock is injected; this closes the residual default-construction path).
        if clock is None:
            try:
                wnode = world.snapshot().node_id
            except Exception:
                wnode = "local"
            clock = NodeLamportClock(wnode)
        self._clock = clock
        if isinstance(world, InMemoryWorldState) and world._clock is not self._clock:
            # ensure the world store uses the SAME shared clock instance
            world._clock = self._clock
        self._node_id = self._clock.node_id
        self._world = world
        self._attention = attention
        self._resources = resources
        self._values = values
        self._decision = decision
        self._executive = executive
        self._learning = learning
        self._planner = planner
        # ТЗ-RE-01: Reasoning Engine is the parametric engine of Deliberate. If none
        # is injected, the kernel has no reasoning step (still legal — Planning runs
        # with empty steps). build_kernel always wires ReferenceReasoningEngine.
        self._reason = reason
        # ТЗ-WM-01: World Model is an ADVISOR to reasoning/decision. If none is
        # injected, reasoning falls back to the word-overlap heuristic.
        self._world_model = world_model
        # ТЗ-ME-01: Memory Evolution is the Learn-phase mechanism of Self-Evolving.
        # It reads episodes from the layered memory and proposes SOFT-layer evolution
        # (semantic facts), guarded by the O1 invariant (HARD layer never evolves).
        self._memory_evolution = memory_evolution
        self._memory = memory
        # ТЗ-RF-01: Reflection Engine is the ANALYTIC part of Self-Evolving. It runs
        # BEFORE Memory Evolution (Learn): reflects on accumulated experience + execution
        # outcomes and PROPOSES SOFT-layer evolution; Memory Evolution commits it under
        # the O1 Self-Evolving guard. Reflection never writes memory itself.
        self._reflection_engine = reflection_engine
        self._embedding = embedding  # Slice: semantic episodic retrieval (K5 reuse of adapters/embedding)
        # Episode-embedding cache: summary -> vector. Avoids re-embedding the same
        # episode summary on every retrieval (perf). Invalidated on record_episode
        # via the memory hook below; rebuilt lazily on next retrieval (not persisted).
        self._embedding_cache: Dict[str, List[float]] = {}
        self._query_cache: Dict[str, List[float]] = {}
        if self._memory is not None:
            self._memory.on_record_episode = self._embedding_cache.clear
        self._outcomes: list = []
        # ТЗ-EX-01: real execution backend (None => proxy fallback, backward compat).
        self._executor = None
        self._last_reflection_report = None
        self._state = CognitiveState.IDLE
        self._goal: Optional[Goal] = None
        self._events: list = []
        self._subscribers: list = []
        self._last_decision = None  # introspection
        self._last_selected_plan = None  # introspection (semantic cognitive-value proof)
        self._federation = None  # ТЗ-NW-01: set by attach_federation
        self._soft_sync = None   # ТЗ-FSE-01: set by attach_soft_memory_sync
        self._metrics = None     # ТЗ-OBS-01: live collector (ILiveMetricsCollector)
        self._supervisor = None   # ТЗ-OBS-01: RuntimeSupervisor (autonomous loop)
        self._metrics_interval = 3  # Флаг 3: step every N ticks (anti-thrash)
        self._tick_no = 0

    # -- event emission (I-17) -------------------------------------------------
    def _emit(self, etype: CognitiveEventType, ref_id: str,
              confidence: ConfidenceScore, actor: str = "kernel") -> None:
        # every local event advances the SHARED node Lamport clock (ТЗ-CAUSAL-01 /
        # ТЗ-RE-01) so emitted CognitiveEvents carry a causally-ordered mark with
        # node_origin = node_id (not a wall-clock timestamp).
        mark = self._clock.tick()
        ev = CognitiveEvent(
            type=etype, ref_id=ref_id,
            provenance=Provenance(source=etype.value, actor=actor),
            confidence=confidence,
            causal=mark,
        )
        self._events.append(ev)
        payload = ev.to_bus()
        for sub in self._subscribers:
            sub(payload)

    # -- FSM transition with Executive gate (I-02) ----------------------------
    def _transition(self, to: CognitiveState, reason: str = "") -> bool:
        if not self._executive.can_transition(self._state.value, to.value):
            return False
        self._state = to
        return True

    # -- ICognitiveKernel ------------------------------------------------------
    def _retrieve_similar_episodes(self, text: str, k: int = 3) -> List["Episode"]:
        """Slice: retrieve past experiences similar to a goal.

        Two paths (K5, no new retrieval engine):
          - semantic: if an ``IEmbedding`` adapter is wired, score by cosine
            similarity over ``Episode.summary`` embeddings (finds synonyms /
            paraphrases that share NO keywords). Adapter failure degrades to [].
          - fallback: dependency-free keyword-overlap (original Slice 3-alt) when
            no embedding adapter is available. Deterministic.
        Both reuse the existing layered-memory Episode store (already persists +
        restores), so retrieval works across restarts. Returns top-k, best-first.
        """
        eps = self._memory.get_episodes() if self._memory is not None else []
        if not eps or not text:
            return []
        if self._embedding is not None:
            return self._retrieve_by_embedding(text, eps, k)
        return self._retrieve_by_keyword(text, eps, k)

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def _retrieve_by_embedding(self, text: str, eps: List["Episode"], k: int) -> List["Episode"]:
        # Query vector: cache by text so identical goals don't re-embed.
        q_key = text or ""
        if q_key in self._query_cache:
            q = self._query_cache[q_key]
        else:
            try:
                q = self._embedding.embed(q_key)
            except Exception:
                return []  # adapter unavailable -> graceful no-retrieval
            self._query_cache[q_key] = q
        scored = []
        for ep in eps:
            key = ep.summary or ""
            if key in self._embedding_cache:
                v = self._embedding_cache[key]  # cache hit: no re-embed
            else:
                try:
                    v = self._embedding.embed(key)
                except Exception:
                    continue
                self._embedding_cache[key] = v  # cache the new summary vector
            sim = self._cosine(q, v)
            if sim >= 0.5:
                scored.append((sim, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:k]]

    def _retrieve_by_keyword(self, text: str, eps: List["Episode"], k: int) -> List["Episode"]:
        goal_tokens = {t for t in re.findall(r"[^\W_]+", text.lower()) if len(t) > 2}
        if not goal_tokens:
            return []
        scored = []
        for ep in eps:
            ep_tokens = {t for t in re.findall(r"[^\W_]+", (ep.summary or "").lower())
                         if len(t) > 2}
            overlap = len(goal_tokens & ep_tokens)
            if overlap > 0:
                scored.append((overlap, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:k]]

    def tick(self, intent: Intent) -> CognitiveState:
        """Advance the FSM one full deliberative cycle (system-2). Returns end state."""
        # Idle -> Observe
        if not self._transition(CognitiveState.OBSERVE):
            return self._state
        # Orient (Attention + ResourceManager)
        if not self._transition(CognitiveState.ORIENT):
            return self._state
        # Deliberate: Planning -> Decision
        if not self._transition(CognitiveState.DELIBERATE):
            return self._state
        goal = Goal(id=_uid("goal"), intent_id=intent.id, description=intent.text,
                    confidence=intent.confidence,
                    provenance=Provenance(source="intent", actor="kernel"))
        self._goal = goal
        self._emit(CognitiveEventType.GOAL_CREATED, goal.id, goal.confidence)
        # Deliberate: Reasoning -> Planning -> Decision (ADR-054 / ТЗ-RE-01)
        # Reasoning reads Intent + WorldState through Attention and yields
        # world-aware reasoning steps (candidates for Planning).
        world_snapshot = self._world.snapshot()
        attention_ctx = self._attention.select_context(intent, world_snapshot, 100)
        steps = self._reason.reason(intent, world_snapshot, attention_ctx, 100) if self._reason else []
        for s in steps:
            self._emit(CognitiveEventType.REASONING_STEP, s.id, s.confidence)
        candidates = self._planner.plan(goal, steps, world_snapshot, 100, intent=intent)
        for p in candidates:
            self._emit(CognitiveEventType.PLAN_GENERATED, p.id, p.confidence)
        # Slice 3-alt: inform planning with retrieved past experience (reuse as
        # CONTEXT, not just a runs-counter). Episodes already persist + restore, so
        # this works across restarts. K5: keyword-overlap over Episode.summary.
        # The retrieved context is folded into EVERY candidate's steps so the
        # DECIDED plan always carries the past-experience reference (provenance-by-step),
        # regardless of which candidate wins. Scoped to goals that already carry a
        # structured execution intent (file/command) so abstract deliberation
        # (choose_blue/red) stays clean. No new port / planner change.
        similar = self._retrieve_similar_episodes(intent.text)
        if similar and any(c.execution_steps for c in candidates):
            ctx = " | ".join(f"past-experience: {ep.summary}" for ep in similar)
            candidates = [
                Plan(id=c.id, goal_id=c.goal_id, steps=c.steps + (ctx,),
                     confidence=c.confidence, provenance=c.provenance,
                     execution_steps=c.execution_steps)
                for c in candidates
            ]
        # flag D: Decision is now world-aware — pass WorldState + Intent so a
        # production engine reads them directly (no bind()-hack).
        decision = self._decision.select(goal, candidates, self._values,
                                         world=world_snapshot, intent=intent)
        self._last_decision = decision  # introspection (K1-clean)
        # introspection: keep the SELECTED Plan object (not just its id) so tests
        # can prove cognitive value by SEMANTICS (steps/description), not by the
        # always-unique plan uuid. ФЛАГ 1 NW-01 strengthening (ТЗ-RT-01 commit 0).
        self._last_selected_plan = next(
            (p for p in candidates if p.id == decision.selected_plan_id), None)
        if decision.selected_plan_id:
            self._emit(CognitiveEventType.DECISION_ACCEPTED, decision.id, decision.confidence)
        else:
            self._emit(CognitiveEventType.DECISION_REJECTED, decision.id, decision.confidence)
            self._transition(CognitiveState.IDLE)
            return self._state
        # Commit
        if not self._transition(CognitiveState.COMMIT):
            return self._state
        # Execute
        if not self._transition(CognitiveState.EXECUTE):
            return self._state
        self._emit(CognitiveEventType.EXECUTION_STARTED, decision.selected_plan_id,
                   decision.confidence)
        # ТЗ-EX-01: REAL execution (closes RF-01 ФЛАГ 2 outcome-proxy).
        if self._executor is not None:
            # chosen Plan -> Action routed to the execution environment
            plan = self._last_selected_plan
            # ТЗ-PHASE-P.3 (ADR-O.9 K6-exception): prefer structured execution intent
            # when the planner emitted one; otherwise fall back to textual steps so the
            # loop stays backward compatible (textual plans still echo via RealWorldExecutor).
            if plan is not None and plan.execution_steps:
                payload = json.dumps([dict(s) for s in plan.execution_steps])
            else:
                payload = "\n".join(plan.steps) if plan is not None else decision.selected_plan_id
            action = Action(
                id=f"act-{decision.selected_plan_id}",
                kind="execute_plan",
                payload=payload,
                confidence=decision.confidence,
                provenance=Provenance(source="decision", actor="kernel"),
            )
            result = self._executor.execute(action)
            # REAL outcome built FROM the raw ExecutionResult (not a proxy).
            outcome = ExecutionOutcome(
                episode_id=decision.id,
                success=result.success,
                utility=result.reward,
                confidence=result.confidence,
                causal=result.causal,
            )
            # ТЗ-OBS-01 hook (no-op if no collector): live execution success rate +
            # rolling consolidation confidence from outcome utility (Флаг 1/2).
            if self._metrics is not None:
                if result.success:
                    self._metrics.record_success(METRIC_EXECUTION_SUCCESS_RATE)
                else:
                    self._metrics.record_failure(METRIC_EXECUTION_SUCCESS_RATE)
                self._metrics.record_raw(METRIC_MEMORY_CONSOLIDATION_CONFIDENCE,
                                         float(result.reward if result.reward is not None else 0.0))
        else:
            # ТЗ-RF-01 proxy fallback (backward compatible): success = decision
            # accepted; utility = decision confidence. Used when no executor wired.
            outcome = ExecutionOutcome(
                episode_id=decision.id,
                success=bool(decision.selected_plan_id),
                utility=decision.confidence.value,
                confidence=decision.confidence,
                causal=self._clock.tick(),
            )
        self._emit(CognitiveEventType.EXECUTION_FINISHED, decision.selected_plan_id,
                   decision.confidence)
        self._outcomes.append(outcome)
        # Evaluate
        if not self._transition(CognitiveState.EVALUATE):
            return self._state
        # ТЗ-RF-01: REFLECTION (analytic) runs BEFORE Learn (executive). It proposes
        # SOFT-layer evolution from accumulated experience + outcomes; Memory Evolution
        # (Learn) is the SOLE writer and commits the proposals under the O1 Self-Evolving
        # guard. Reflection NEVER writes memory itself (ADR-060 §2: analytic vs executive).
        self._last_reflection_report = None
        if self._reflection_engine is not None and self._memory is not None:
            report = self._reflection_engine.reflect(
                self._memory, world_snapshot, outcomes=self._outcomes)
            self._emit(CognitiveEventType.REFLECTION_COMPLETED,
                       "reflection", report.confidence)
            # store the report; Memory Evolution (Learn) is the ONLY writer that commits
            # it. No commit_semantic here — avoids duplicate writes (ФЛАГ 1, ТЗ-NW-01).
            self._last_reflection_report = report
        # Learn
        if not self._transition(CognitiveState.LEARN):
            return self._state
        # legacy ILearningPolicy propose/accepts (kept for backward compatibility)
        proposal = self._learning.propose([decision.id])
        if proposal and self._learning.accepts(proposal):
            self._emit(CognitiveEventType.POLICY_UPDATED, proposal.id, proposal.confidence)
        # ТЗ-ME-01: Memory Evolution — the SOLE writer of the SOFT layer. It turns THIS
        # decision into an episode, consolidates repeated high-confidence experience into
        # semantic facts, AND applies the Reflection report (ТЗ-RF-01) — all under the O1
        # Self-Evolving guard. Single write path => no duplicate consolidation (ФЛАГ 1).
        if self._memory_evolution is not None and self._memory is not None:
            from contracts.i_cognitive_kernel import IValueSystem
            plan = self._last_selected_plan
            exec_steps = plan.execution_steps if plan is not None else None
            exec_part = ""
            if exec_steps:
                exec_part = "||exec:" + ";".join(
                    f"{s.get('kind')}:{s.get('path') or s.get('cmd') or ''}"
                    for s in exec_steps if isinstance(s, dict)
                )
            episode = Episode(
                id=decision.id, summary=f"decided:{'|'.join(plan.steps)}" + exec_part,
                confidence=decision.confidence,
                provenance=Provenance(source="learn", actor="kernel"),
            )
            self._memory.record_episode(episode)
            facts, soft_policies = self._memory_evolution.consolidate(
                self._memory.get_episodes())
            # ТЗ-OBS-01 hook (no-op if no collector): count new consolidated facts as
            # memory growth this tick (for memory.growth_rate_per_tick).
            if self._metrics is not None:
                self._metrics.record_episode_growth(len(facts))
            # Merge ME-01 facts + Reflection consolidation candidates, then DEDUPLICATE by
            # content so one experience is consolidated exactly once (ФЛАГ 1, ТЗ-NW-01).
            # Dedupe against BOTH this tick's candidates AND already-committed semantic
            # facts, so repeated ticks never re-consolidate the same experience.
            candidates = list(facts)
            if self._last_reflection_report is not None:
                candidates.extend(self._last_reflection_report.consolidation_candidates)
            seen: set = {f.content for f in self._memory.get_semantic()}
            for c in candidates:
                if c.content in seen:
                    continue  # dedupe: same experience already consolidated (ME-01 or Reflection)
                seen.add(c.content)
                # Self-Evolving guard (O1): never evolve HARD; check hard_violations before
                # committing any SOFT/semantic proposal.
                if self._values is not None and self._values.hard_violations(c):
                    continue  # reject — would violate a KROFT Law
                self._memory.commit_semantic(c)
                self._emit(CognitiveEventType.SEMANTIC_CONSOLIDATED, c.id, c.confidence)
            # Флаг 2 fix (ТЗ-RF-01): soft_policies из consolidate коммитятся в normative
            # с тем же O1 guard — HARD policy отвергается, только SOFT попадают.
            for sp in soft_policies:
                if sp.layer != "soft":
                    continue  # O1: HARD layer never evolves from experience
                if self._values is not None and self._values.hard_violations(sp):
                    continue  # reject — would violate a KROFT Law
                self._memory.commit_normative(sp)
                self._emit(CognitiveEventType.POLICY_UPDATED, sp.id, sp.confidence)
            # forgetting: deprecate low-confidence / stale episodes (and Reflection's
            # deprecation_candidates).
            deprecated = self._memory_evolution.forget(self._memory.get_episodes())
            if self._last_reflection_report is not None:
                deprecated = deprecated + list(self._last_reflection_report.deprecation_candidates)
            # ТЗ-SE-01 (ФЛАГ 3 closure): repeated FAILURE -> deprecation_candidates
            # (e.g. 'decided:X'). Turn each into a SOFT 'avoid:<pattern>' policy so the
            # next deliberation PENALIZES that candidate (behavior changes, not just
            # memory). Dedup against already-committed soft policies. O1: layer=='soft'.
            for d in (self._last_reflection_report.deprecation_candidates
                      if self._last_reflection_report is not None else ()):
                avoid_body = f"avoid:{d}"
                already = any(getattr(p, "layer", None) == "soft" and p.body == avoid_body
                             for p in self._memory.get_normative())
                if already:
                    continue
                avoid_policy = Policy(
                    id=f"soft-avoid-{abs(hash(d)) % 10_000}",
                    name=f"avoid:{d}",
                    layer="soft",
                    body=avoid_body,
                    confidence=ConfidenceScore(0.7, ProvenanceType.REFLECTION),
                    provenance=Provenance(source="self_evolution", actor="kernel"),
                )
                if self._values is not None and self._values.hard_violations(avoid_policy):
                    continue  # O1: never evolve HARD
                self._memory.commit_normative(avoid_policy)
                self._emit(CognitiveEventType.POLICY_UPDATED, avoid_policy.id,
                           avoid_policy.confidence)
            if deprecated:
                self._emit(CognitiveEventType.NORMATIVE_DEPRECATED, deprecated[0],
                           ConfidenceScore(0.1, ProvenanceType.OBSERVATION))
            # ТЗ-FSE-01: replicate the EVOLVED SOFT layer to peers after local learning.
            # Inbound federated items merge into ILayeredMemory (receiver side of
            # FederationSoftMemorySync) and influence the NEXT Decision via the SE-01
            # read-side (MemorySoftPolicySource / KnowledgeAwareReasoning). HARD is never
            # shipped (O1, enforced inside publish_soft_layer). Optional: no-op without
            # a wired sync.
            if self._soft_sync is not None and self._memory is not None:
                self._soft_sync.publish_soft_layer(self._memory, self._node_id)
            # ТЗ-OBS-01: autonomous runtime adaptation from LIVE metrics (closes RT-01
            # debt). Every N ticks (Флаг 3: anti-thrash) run the supervisor loop
            # collect->reflect->apply; hooks above fed LIVE counters this tick. No-op
            # without a wired supervisor.
            if self._metrics is not None:
                self._metrics.record_tick()
            if self._supervisor is not None:
                self._tick_no += 1
                if self._tick_no % self._metrics_interval == 0:
                    self._supervisor.step()
        # back to Idle
        self._transition(CognitiveState.IDLE)
        return self._state

    def run_system1(self, observation: Observation) -> None:
        """Reactive LLM-free path (I-09/I-16): Observe->Orient->(rule)->Execute.

        Follows the allowed FSM transitions (IDLE->OBSERVE->ORIENT->EXECUTE),
        all deterministic and WITHOUT an LLM call (system-1 shortcut).
        """
        self._world.update(observation)
        self._state = CognitiveState.OBSERVE
        self._emit(CognitiveEventType.OBSERVATION_RECEIVED, observation.id,
                   observation.confidence)
        if not self._transition(CognitiveState.ORIENT):
            self._state = CognitiveState.IDLE
            return
        # rule-based execution without LLM (system-1)
        if self._transition(CognitiveState.EXECUTE):
            self._emit(CognitiveEventType.EXECUTION_STARTED, observation.id,
                       observation.confidence)
            self._emit(CognitiveEventType.EXECUTION_FINISHED, observation.id,
                       observation.confidence)
        self._state = CognitiveState.IDLE

    def on_event(self, handler: Callable[[dict], None]) -> None:
        self._subscribers.append(handler)

    # -- federation (ТЗ-NW-01) ------------------------------------------------
    def attach_federation(self, federation: "object") -> None:
        """Wire a NetworkFederationService so inbound federated WorldState merges into
        the local SSOT and influences the NEXT Decision (FEDERATION COGNITIVE VALUE).

        Idempotent: re-attaching the same service is a no-op. On every causal merge the
        federation service calls back into ``_on_federated_world``, which folds the
        merged world into ``self._world`` — so the next ``tick`` reads the federated
        facts through ``world.snapshot()``. The receiver callback is locked after bind
        (ТЗ-NW-01 flag 1) so a later override cannot silently drop the SSOT fold.
        """
        if self._federation is federation:
            return  # idempotent: already wired
        self._federation = federation
        if hasattr(federation, "set_local_world"):
            federation.set_local_world(self._world.snapshot())
        # NetworkFederationService stores the receiver callback in _on_world_merged;
        # bind it to our local-SSOT fold. (Public on_world_merged setter if present.)
        setter = getattr(federation, "on_world_merged", None)
        if setter is not None:
            setter(self._on_federated_world)
        else:
            object.__setattr__(federation, "_on_world_merged", self._on_federated_world)
        # finalize: any later override of the receiver is ignored (flag 1)
        locker = getattr(federation, "lock_receiver", None)
        if locker is not None:
            locker()
        # VERIFY the wiring (flag 1): the federation receiver must be our SSOT fold.
        # Bound methods are re-created on each attribute access, so compare by
        # underlying function + bound instance, NOT by identity (`is`).
        recv = federation.receiver
        wired = (recv is not None
                 and recv.__func__ is self._on_federated_world.__func__
                 and recv.__self__ is self)
        assert wired, "attach_federation: receiver callback not wired to kernel SSOT fold"
        assert federation.has_receiver, "attach_federation: receiver callback missing"

    def attach_soft_memory_sync(self, sync: "object") -> None:
        """ТЗ-FSE-01: wire a FederationSoftMemorySync so the EVOLVED SOFT layer (semantic
        facts + soft policies) is replicated to peers after local learning, and inbound
        federated SOFT items merge into the local ILayeredMemory (influencing the NEXT
        Decision via the SE-01 read-side).

        Idempotent: re-attaching the same sync is a no-op. The receiver is locked after
        bind (ТЗ-NW-01 flag 1 analog) so a later override cannot silently drop the merge.
        """
        if self._soft_sync is sync:
            return  # idempotent: already wired
        self._soft_sync = sync
        # the sync already subscribed its receiver to transport.on_soft_layer in __init__;
        # lock it so external override is ignored (flag 1)
        locker = getattr(sync, "lock_receiver", None)
        if locker is not None:
            locker()

    def attach_live_metrics(self, collector: "object", supervisor: "object") -> None:
        """ТЗ-OBS-01: wire a live metrics collector (ILiveMetricsCollector) + optional
        RuntimeSupervisor. Hook-points in tick() record operational counters; the
        supervisor runs the autonomous collect->reflect->apply loop every N ticks (Флаг 3).
        No-op semantics: with no collector the kernel behaves EXACTLY as before (hooks
        are skipped)."""
        self._metrics = collector
        self._supervisor = supervisor

    def attach_executor(self, executor: "object") -> None:
        """ТЗ-EX-01: wire a real execution backend (IExecutor).

        When set, the Execute-phase runs the chosen plan through `executor.execute`
        and records the REAL ExecutionResult as the Reflection Outcome (closing the
        RF-01 outcome-proxy). When None, the kernel falls back to the proxy outcome
        (backward compatible — existing tests without an executor keep working).
        """
        self._executor = executor

    def _on_federated_world(self, merged: "WorldState") -> None:
        """Receiver hook: fold a causally-merged remote WorldState into the local SSOT."""
        self._world.apply_remote(merged)
        self._emit(CognitiveEventType.OBSERVATION_RECEIVED, "federated",
                   ConfidenceScore(0.9, ProvenanceType.OBSERVATION))

    # -- introspection ---------------------------------------------------------
    @property
    def state(self) -> CognitiveState:
        return self._state

    @property
    def events(self) -> List[CognitiveEvent]:
        return list(self._events)


def build_kernel(node_id: str = "local", clock: Optional[NodeLamportClock] = None,
                 llm_client: Optional[object] = None,
                 live_metrics: Optional[object] = None,
                 config: Optional["KernelConfig"] = None,
                 memory: Optional[object] = None,
                 procedural: Optional[object] = None,
                 embedding: Optional[object] = None) -> CognitiveKernel:
    """Factory: assemble a deterministic, LLM-free reference kernel (I-09).

    Backward-compatible thin wrapper. All composition logic now lives in ``KernelBuilder``
    (kernel/kernel_builder.py) so this factory stops growing per-ТЗ (ТЗ-OBS-01 Флаг 1: the
    old god-factory accumulated optional params + inline ``if ... is not None`` + post-hoc
    ``attach_*`` blocks). New optional subsystems are added as a ``KernelConfig`` field +
    a branch in ``KernelBuilder``, NOT as a new positional/keyword argument here.

    Behaviour is identical to the pre-refactor build:
    - ONE shared Lamport clock per node (injected into world + reasoning/planner/world-model/
      reflection) so CausalMarks share causal order + node_origin == node_id.
    - LLM-free by construction; optional ``llm_client`` wrapped behind ILLMAdvisor (adapter_for);
      when None the advisor wrappers degrade to the pure reference path.
    - Optional ``live_metrics`` wires the live collector + RuntimeSupervisor (no-op if None).
    - Optional ``memory`` / ``procedural`` inject pre-loaded stores so the kernel can RESUME
      across restarts (ТЗ-LIVE-01); when None fresh in-memory stores are created.
    - Explicit kwargs WIN over a passed ``config`` object.
    """
    base = config if config is not None else KernelConfig()
    resolved = base.merged(node_id=node_id, clock=clock,
                           llm_client=llm_client, live_metrics=live_metrics,
                           memory=memory, procedural=procedural, embedding=embedding)
    from kernel.kernel_builder import KernelBuilder
    return KernelBuilder(resolved).build()
