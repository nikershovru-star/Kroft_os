"""AgentLoop — iterative goal-driven agent cycle (ТЗ-AGENT-LOOP-01, ADR-090, reference impl).

K6: lives in kernel/ (its own layer) — imports ONLY kernel.* + contracts.* + stdlib.
Builds a kernel via build_kernel (same seam ReferenceAgentExecutor uses), then drives
CognitiveKernel.tick repeatedly with observation-feedback until the goal is met (kernel
stops producing a plan) or the step budget is exhausted. LLM-free by default (I-09): the
tick is deterministic, so the loop is reproducible without a model.

Feedback loop (the core of ТЗ-AGENT-LOOP-01): each step's intent text carries the prior
observations, so the planner/decision see what already happened and re-plan against it.
Memory accumulates across steps (one kernel for the whole loop) and is surfaced as
memory_delta (observations + fact/skill/trust snapshot via JsonMemoryStore).

O1: failures are caught and returned as AgentLoopResult(success=False) — never a crash.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from contracts.cognitive_domain import (
    ConfidenceScore,
    Intent,
    Observation,
    Episode,
    Provenance,
    ProvenanceType,
)
from contracts.i_agent_loop import AgentLoopResult, IAgentLoop
from contracts.i_skill_evolver import ISkillEvolver, SkillUsageStats
from contracts.i_memory import IProceduralMemory

from kernel.cognitive_kernel import build_kernel
from kernel.execution import ReferenceExecutor


class AgentLoop(IAgentLoop):
    """Iterative goal-driven loop over a single cognitive kernel (ТЗ-AGENT-LOOP-01).

    L10.8 (CORE AUTONOMOUS EVOLUTION): the loop is also a SELF-EVOLVING runtime.
    When an injected ``skill_evolver`` + ``procedural_memory`` are present, the loop
    AUTONOMOUSLY triggers skill evolution after each step — it discovers a weakness
    (a step that did not produce a plan / weak outcome), forms an improvement
    hypothesis via ``SkillEvolver`` (propose -> sandbox-test -> promote/reject), and
    persists the promoted skill. On the NEXT run for the same capability the loop
    reads the evolved (version+1) skill and feeds it back into the planner as a
    known-good procedure, so the improved behaviour is actually used. No meta-layer,
    no external daemon: evolution lives INSIDE the existing kernel loop and reuses
    SkillEvolver + procedural memory + the existing snapshot persistence. Humans
    only ever call ``run(goal)`` — they never call ``evolve()``.
    """

    def __init__(self, node_id: str = "agent-loop", llm_client=None,
                 timeout: float = 30.0, kernel=None, knowledge_index=None,
                 memory=None, embedding=None,
                 skill_evolver: Optional[ISkillEvolver] = None,
                 procedural_memory: Optional[IProceduralMemory] = None) -> None:
        self._node_id = node_id
        self._llm_client = llm_client
        self._timeout = timeout
        self._kernel = kernel
        self._knowledge_index = knowledge_index
        self._memory = memory  # ТЗ-L10: share run_kroft's layered memory so loop learning persists
        self._embedding = embedding  # ТЗ-L10.4: reuse existing EmbeddingAdapter for semantic episodic retrieval
        # L10.8: injected evolution subsystem (backward-compat: None -> evolution disabled)
        self._skill_evolver = skill_evolver
        self._procedural_memory = procedural_memory

    def run(self, goal: str, budget: int = 5) -> AgentLoopResult:
        if budget < 1:
            return AgentLoopResult(success=False, steps_taken=0,
                                   final_outcome="", memory_delta=(),
                                   error="budget must be >= 1")
        kernel = self._kernel if self._kernel is not None else build_kernel(
            self._node_id, llm_client=self._llm_client,
            knowledge_index=self._knowledge_index,
            memory=self._memory,
            embedding=self._embedding)
        self._kernel = kernel  # keep reference so feedback writes to the live world
        kernel.attach_executor(ReferenceExecutor())

        observations: List[str] = []
        steps = 0
        final_outcome = ""
        try:
            for step in range(budget):
                # L10.8: AUTONOMOUS evolution trigger at the START of every step —
                # the loop discovers a WEAK skill for this capability (measured sandbox
                # score) and evolves it BEFORE ticking, so the improvement is in place
                # for this very run and (via _evolved_procedure_hint) fed back to the
                # planner. Runs regardless of whether the subsequent tick succeeds or
                # raises (O1: a tick fault must not suppress evolution, nor vice-versa).
                self._evolve_if_needed(goal)
                # Feedback: the intent carries prior RETRIEVED knowledge (real outcome of
                # previous ticks) so the next reasoning/retrieval is grounded in it — without
                # polluting retrieval with the full observation log. Observations are still
                # recorded locally for the result trail.
                prior_knowledge = [
                    s for s in observations if isinstance(s, str) and s.startswith("knowledge:")
                ]
                intent_text = goal
                if prior_knowledge:
                    intent_text = goal + "\n\nPrior knowledge from earlier steps:\n" + "\n".join(
                        f"- {k}" for k in prior_knowledge[-3:]
                    )
                # L10.8: feed the EVOLVED skill (version+1) for this capability back
                # into the planner as a known-good procedure so the improved behaviour
                # is actually USED on the next run (not just stored).
                evolved_hint = self._evolved_procedure_hint(goal)
                if evolved_hint:
                    intent_text = intent_text + evolved_hint
                intent = Intent(
                    id=f"{self._node_id}-step-{step}",
                    text=intent_text,
                    confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="agent-loop", actor="agent-loop"),
                )
                kernel.tick(intent)
                plan = kernel._last_selected_plan
                outcome = "|".join(plan.steps) if plan is not None else "no-plan"
                observations.append(f"step {steps + 1}: {outcome}")
                # ТЗ-L8 feedback: fold the REAL retrieved knowledge from this tick into
                # the kernel's WorldState so the NEXT tick's reasoning is grounded in it.
                # Only real retrieved content (lines "knowledge: <node>: <snippet>") is
                # added — never synthetic text. This is what makes Plan N+1 differ from Plan N.
                if plan is not None:
                    for s in plan.steps:
                        if isinstance(s, str) and s.startswith("knowledge:"):
                            try:
                                kernel._world.update(
                                    Observation(
                                        id=f"{self._node_id}-obs-{steps + 1}",
                                        content=s,
                                        confidence=ConfidenceScore(0.8, ProvenanceType.OBSERVATION),
                                        provenance=Provenance(source="agent-loop", actor="agent-loop"),
                                    )
                                )
                            except Exception:
                                pass  # observation write must never break the loop
                steps += 1
                final_outcome = outcome
                # Stop when the kernel stops producing a plan (goal reached / no further plan).
                if plan is None:
                    break
        except Exception as exc:  # noqa: BLE001 — loop faults must be graceful, not crash
            memory_delta = self._memory_delta(kernel, observations)
            return AgentLoopResult(
                success=False, steps_taken=steps, final_outcome=final_outcome,
                memory_delta=memory_delta, error=f"{type(exc).__name__}: {exc}",
            )

        memory_delta = self._memory_delta(kernel, observations)
        return AgentLoopResult(
            success=True, steps_taken=steps, final_outcome=final_outcome,
            memory_delta=memory_delta,
        )

    @staticmethod
    def _memory_delta(kernel, observations: List[str]) -> Tuple[str, ...]:
        """Surface what changed in memory: observations + world-fact count (best-effort).

        Uses the public ``kernel.snapshot()`` (WorldState.facts) — no private access.
        Observations accumulate across steps (the feedback-loop trail); the world fact
        count shows the kernel's memory grew during the loop.
        """
        delta: List[str] = list(observations)
        try:
            world = kernel.snapshot()
            facts = getattr(world, "facts", None)
            if facts:
                delta.append(f"facts={len(facts)}")
        except Exception:
            pass  # memory introspection is best-effort; loop still returns observations
        return tuple(delta)

    # --- L10.8: CORE AUTONOMOUS EVOLUTION (inside the kernel loop) ---------------
    @staticmethod
    def _capability_of(goal: str) -> str:
        """Map a goal to its capability key (used to look up / evolve the skill)."""
        return goal.strip().split()[0] if goal.strip() else goal.strip()

    def _evolved_procedure_hint(self, goal: str) -> str:
        """Return a planner hint containing the EVOLVED skill for this capability.

        On the NEXT run after a promotion the stored skill is version+1 (shorter /
        more reliable); feeding it back makes the improved behaviour actually USED.
        Returns "" when evolution is disabled or no skill exists yet.
        """
        if self._procedural_memory is None:
            return ""
        cap = self._capability_of(goal)
        skill = self._procedural_memory.recall_skill_by_capability(cap)
        if skill is None:
            return ""
        steps = "\n".join(f"- {s}" for s in skill.steps)
        return (f"\n\nKnown-good procedure v{skill.version} for '{cap}':\n{steps}")

    def _evolve_if_needed(self, goal: str) -> None:
        """AUTONOMOUS evolution trigger. The loop itself discovers a weakness and
        evolves the skill — humans never call this.

        Closed loop (reuses SkillEvolver, ТЗ-EVOLUTION-01):
          weakness (MEASURED sandbox score) -> propose candidate (drop weakest step)
          -> sandbox-test -> promote (version+1, store_skill) only if BETTER than
          baseline, else reject (skill unchanged). Evolution never mutates production
          on a rejection, and never breaks the runtime loop (O1: exceptions swallowed).
        """
        if self._skill_evolver is None or self._procedural_memory is None:
            return  # evolution disabled (backward-compat)
        cap = self._capability_of(goal)
        skill = self._procedural_memory.recall_skill_by_capability(cap)
        if skill is None:
            return  # nothing to evolve for this capability
        # MEASURABLE weakness: score the skill itself in the sandbox (the same
        # deterministic metric the candidate is tested against). This is honest
        # self-assessment — NOT "the planner returned a plan" and NOT "no exception".
        success_rate = self._skill_evolver.measure_skill(skill)
        stats = SkillUsageStats(
            capability=cap,
            uses=1,
            success_rate=success_rate,
        )
        try:
            self._skill_evolver.evolve_skill(skill, stats)
        except Exception:
            pass  # O1: evolution must never break the runtime loop
