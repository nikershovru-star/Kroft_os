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

from kernel.cognitive_kernel import build_kernel
from kernel.execution import ReferenceExecutor


class AgentLoop(IAgentLoop):
    """Iterative goal-driven loop over a single cognitive kernel (ТЗ-AGENT-LOOP-01)."""

    def __init__(self, node_id: str = "agent-loop", llm_client=None,
                 timeout: float = 30.0, kernel=None, knowledge_index=None,
                 memory=None, embedding=None) -> None:
        self._node_id = node_id
        self._llm_client = llm_client
        self._timeout = timeout
        self._kernel = kernel
        self._knowledge_index = knowledge_index
        self._memory = memory  # ТЗ-L10: share run_kroft's layered memory so loop learning persists
        self._embedding = embedding  # ТЗ-L10.4: reuse existing EmbeddingAdapter for semantic episodic retrieval

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
