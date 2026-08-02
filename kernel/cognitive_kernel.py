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
from typing import Callable, Dict, List, Optional

from contracts.cognitive_domain import (
    CausalMark,
    CognitiveEvent,
    CognitiveEventType,
    CognitiveState,
    ConfidenceScore,
    Decision,
    Episode,
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
from kernel.reasoning import ReferenceReasoningEngine
from kernel.world_model import ReferenceWorldModel
from kernel.planning import ReferencePlanner
from kernel.memory_evolution import ReferenceMemoryEvolution
from kernel.memory_store import InMemoryLayeredMemory


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


class SimpleValueSystem(IValueSystem):
    """Two-layer (I-11/I-19): hard veto from a set of violated-constraint checkers."""

    def __init__(self, hard_checkers: Optional[List[Callable[[object], Optional[str]]]] = None,
                 weights: Optional[Dict[str, float]] = None) -> None:
        self._hard = hard_checkers or []
        self._weights = weights or {"confidence": 1.0, "cost": -0.2, "risk": -0.5}

    def hard_violations(self, candidate: object) -> List[str]:
        out = []
        for chk in self._hard:
            v = chk(candidate)
            if v:
                out.append(v)
        return out

    def score(self, candidate: object) -> float:
        # soft utility: weighted sum of attributes (confidence/cost/risk)
        c = getattr(candidate, "confidence", None)
        base = c.value if isinstance(c, ConfidenceScore) else 0.5
        return base * self._weights.get("confidence", 1.0)


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
                 memory: Optional["ILayeredMemory"] = None) -> None:
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
        self._state = CognitiveState.IDLE
        self._goal: Optional[Goal] = None
        self._events: list = []
        self._subscribers: list = []
        self._last_decision = None  # introspection

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
        # flag D: Decision is now world-aware — pass WorldState + Intent so a
        # production engine reads them directly (no bind()-hack).
        decision = self._decision.select(goal, candidates, self._values,
                                         world=world_snapshot, intent=intent)
        self._last_decision = decision  # introspection (K1-clean)
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
        self._emit(CognitiveEventType.EXECUTION_FINISHED, decision.selected_plan_id,
                   decision.confidence)
        # Evaluate
        if not self._transition(CognitiveState.EVALUATE):
            return self._state
        # Learn
        if not self._transition(CognitiveState.LEARN):
            return self._state
        # legacy ILearningPolicy propose/accepts (kept for backward compatibility)
        proposal = self._learning.propose([decision.id])
        if proposal and self._learning.accepts(proposal):
            self._emit(CognitiveEventType.POLICY_UPDATED, proposal.id, proposal.confidence)
        # ТЗ-ME-01: Memory Evolution — turn THIS decision into an episode, then
        # consolidate repeated high-confidence experience into SOFT semantic facts
        # (guarded by the Self-Evolving invariant: HARD layer never evolves).
        if self._memory_evolution is not None and self._memory is not None:
            from contracts.i_cognitive_kernel import IValueSystem
            episode = Episode(
                id=decision.id, summary=f"decided:{intent.text}",
                confidence=decision.confidence,
                provenance=Provenance(source="learn", actor="kernel"),
            )
            self._memory.record_episode(episode)
            facts, soft_policies = self._memory_evolution.consolidate(
                self._memory.get_episodes())
            for f in facts:
                # Self-Evolving guard (O1): never evolve HARD; check hard_violations
                # before committing any normative/soft proposal. Semantic facts are
                # SOFT by construction, but we still re-assert the guard here.
                if self._values is not None and self._values.hard_violations(f):
                    continue  # reject — would violate a KROFT Law
                self._memory.commit_semantic(f)
                self._emit(CognitiveEventType.SEMANTIC_CONSOLIDATED, f.id, f.confidence)
            # forgetting: deprecate low-confidence / stale episodes
            deprecated = self._memory_evolution.forget(self._memory.get_episodes())
            if deprecated:
                self._emit(CognitiveEventType.NORMATIVE_DEPRECATED, deprecated[0],
                           ConfidenceScore(0.1, ProvenanceType.OBSERVATION))
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

    # -- introspection ---------------------------------------------------------
    @property
    def state(self) -> CognitiveState:
        return self._state

    @property
    def events(self) -> List[CognitiveEvent]:
        return list(self._events)


def build_kernel(node_id: str = "local", clock: Optional[NodeLamportClock] = None) -> CognitiveKernel:
    """Factory: assemble a deterministic, LLM-free reference kernel (I-09).

    ТЗ-RE-01 flag 1: ONE shared Lamport clock per node. The same clock instance is
    injected into the world store AND the kernel so all emitted CausalMarks carry
    the same causal order + node_origin = node_id (never the literal "kernel").
    """
    shared_clock = clock if clock is not None else NodeLamportClock(node_id)
    world = InMemoryWorldState(node_id, clock=shared_clock)
    res = SimpleResourceManager()
    attn = SimpleAttention(res)
    val = SimpleValueSystem()
    dec = DeterministicDecisionEngine()
    exec_ = DeterministicExecutive(res)
    learn = SimpleLearningPolicy()
    # ТЗ-RE-01: Reasoning Engine wired with the SAME shared node clock (flag 1) so
    # reasoning steps carry the node's causal order + node_origin = node_id.
    reason = ReferenceReasoningEngine(shared_clock, attn)
    # ТЗ-WM-01: World Model is an ADVISOR over world state, sharing the same clock.
    # Wired into the Reasoning Engine so grounded steps are ranked by PREDICTED
    # utility (not word overlap). The deterministic Decision still makes the final pick.
    world_model = ReferenceWorldModel(shared_clock)
    # ТЗ-PL-01: Autonomous Planner — a real Deliberate-phase component (not a lambda).
    # Generates candidates from reasoning steps, runs each through the World Model
    # (lookahead via simulate), and ranks by PREDICTED VALUE-AWARE utility (flag 2).
    # The planner only ranks; the deterministic Decision makes the final pick (I-03).
    planner = ReferencePlanner(shared_clock, world_model=world_model, values=val)
    # ТЗ-ME-01: Memory Evolution — Learn-phase mechanism of Self-Evolving.
    # SOFT-layer consolidation (semantic facts) from repeated high-confidence episodes;
    # HARD layer is immutable from experience (O1 guard).
    memory = InMemoryLayeredMemory()
    memory_evolution = ReferenceMemoryEvolution(shared_clock)

    return CognitiveKernel(world, attn, res, val, dec, exec_, learn, planner,
                           clock=shared_clock, reason=reason, world_model=world_model,
                           memory_evolution=memory_evolution, memory=memory)
