"""Agent Loop port — iterative goal-driven agent cycle (ТЗ-AGENT-LOOP-01, ADR-090).

K1-compliant: stdlib + contracts only. K5: this is a NEW boundary (iterative loop), NOT a
duplicate of IAgentPlatform (ADR-014, single-shot mission orchestration returning one
AgentResult) nor IAgentExecutor (ADR-080, ONE tick -> TaskOutcome) nor ILlm/ILLMAdvisor.
The loop drives the kernel tick repeatedly with observation-feedback until the goal is met
or a step budget is exhausted, accumulating a memory delta.

K5 recon result (commit 0): IAgentPlatform.run orchestrates Planner+Memory+...+Workflow in
ONE call (no budget, no inter-step observation feedback). IAgentExecutor.execute runs ONE
tick. ReferenceAgentExecutor is one tick. NONE is an iterative goal-driven loop -> IAgentLoop
is the missing seam; no existing port is duplicated.

The loop is LLM-free by default (I-09): a deterministic cognitive tick needs no model. A
live model is advisory only. O1: the loop is a SWAPPABLE driver; failure -> graceful
AgentLoopResult(success=False), never a crash.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class AgentLoopResult:
    """Frozen outcome of one agent loop run (ТЗ-AGENT-LOOP-01).

    Carries the loop-level evidence trail: how many steps were taken, the final outcome
    text, and what changed in memory across steps (observations + fact/skill/trust deltas).
    Frozen like AgentResult (ADR-014) — a run is data, not a side effect.
    """

    success: bool
    steps_taken: int
    final_outcome: str
    memory_delta: Tuple[str, ...] = ()
    error: str = ""

    def with_memory(self, *deltas: str) -> "AgentLoopResult":
        return self.__class__(**{
            **self.__dict__,
            "memory_delta": self.memory_delta + tuple(deltas),
        })


class IAgentLoop(ABC):
    """Port: run an iterative goal-driven agent loop (ТЗ-AGENT-LOOP-01).

    Contract:
      - ``run(goal, budget)`` iterates the underlying cognitive tick with observation
        feedback: plan(goal + prior observations) -> execute -> observe(outcome) ->
        reflect -> update memory -> next step, until success OR budget exhausted.
      - Deterministic (I-09) when LLM-free: same goal + budget -> same steps/outcome.
      - On unrecoverable failure MUST return AgentLoopResult(success=False), NOT raise —
        the caller falls back gracefully (O1).
      - MUST NOT mutate HARD/FSM; it only drives ticks and reads memory deltas.
    """

    @abstractmethod
    def run(self, goal: str, budget: int = 5) -> AgentLoopResult:
        """Iterate toward ``goal`` up to ``budget`` ticks; return a frozen result."""
        raise NotImplementedError
