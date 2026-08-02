"""Cognitive Kernel ports (ADR-054 — Cognitive Kernel Constitution).

K1-compliant: stdlib + contracts ONLY. No service/adapter/runtime imports.
Defines the cross-cutting contracts and phase ports of the Cognitive FSM:

  - IAttention        (I-05) cognitive selector — NOT resource manager
  - IResourceManager   (I-06) budget/quota enforcement — separate from Attention
  - IValueSystem       (I-11/I-19) hard veto (Normative) + soft utilities (K1..K8)
  - IDecisionEngine    (I-03) DETERMINISTIC selector (LLM = advisor only)
  - IExecutive         (I-02) SOLE transition authority / FSM controller
  - ILearningPolicy    (I-14) Learning proposes, does not write memory directly
  - IWorldState        (I-07) local node single source of truth
  - ICognitiveKernel   (I-01) orchestrator wiring the FSM

Every port is deterministic (LLM-free core, I-09) unless it explicitly takes an
ILlm advisor — and even then the DECISION/SELECTION stays rule/policy-based.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from contracts.cognitive_domain import (
    ConfidenceScore,
    CausalMark,
    Decision,
    Goal,
    Intent,
    Observation,
    Plan,
    Policy,
    Provenance,
    ReasoningStep,
    WorldState,
)


# --------------------------------------------------------------------------
# Attention (I-05) — cognitive selector. NOT a resource manager.
# --------------------------------------------------------------------------
class IAttention(ABC):
    """Selects WHAT to focus on (context assembly). Queries IResourceManager for quota."""

    @abstractmethod
    def select_context(self, intent: Intent, world: WorldState,
                       budget_tokens: int) -> List[str]:
        """Return focused context item ids (max within budget)."""

    @abstractmethod
    def salience(self, item_id: str, intent: Intent, world: WorldState) -> ConfidenceScore:
        """Cognitive salience of an item (novelty x uncertainty x goal-relevance)."""


# --------------------------------------------------------------------------
# Resource Manager (I-06) — budget/quota enforcement. Separate from Attention.
# --------------------------------------------------------------------------
class IResourceManager(ABC):
    """Enforces compute budgets: tokens, LLM calls, agents, memory, search (LLM-free)."""

    @abstractmethod
    def request_quota(self, requester: str, kind: str, amount: int) -> int:
        """Return GRANTED amount (<= amount). Deterministic, no LLM."""

    @abstractmethod
    def remaining(self, kind: str) -> int: ...


# --------------------------------------------------------------------------
# Value System (I-11 / I-19) — executable KROFT Laws as values.
# --------------------------------------------------------------------------
class IValueSystem(ABC):
    """Two-layer: hard veto (Normative, K1..K8) + soft utilities (trade-off)."""

    @abstractmethod
    def hard_violations(self, candidate: object) -> List[str]:
        """Return list of violated HARD constraints (empty = ok to evaluate)."""

    @abstractmethod
    def score(self, candidate: object) -> float:
        """Soft utility score (higher better). Only called on hard-valid candidates."""


# --------------------------------------------------------------------------
# Decision Engine (I-03) — DETERMINISTIC selector. LLM = advisor only.
# --------------------------------------------------------------------------
class IDecisionEngine(ABC):
    """Selects the ONE plan from planner candidates by expected utility.

    The selection MUST be deterministic (rule/policy-based). An ILlm may advise a
    risk estimate, but the final pick is NOT an LLM call (protects autonomy, I-09).
    """

    @abstractmethod
    def select(self, goal: Goal, candidates: List[Plan],
               values: IValueSystem) -> Decision:
        """Deterministic expected-utility selection. Rejects hard-violating plans."""


# --------------------------------------------------------------------------
# Executive (I-02) — SOLE transition authority / FSM controller.
# --------------------------------------------------------------------------
class IExecutive(ABC):
    """Controls FSM transitions. NEVER does reasoning. Decides when LLM vs rules."""

    @abstractmethod
    def can_transition(self, frm: str, to: str) -> bool: ...

    @abstractmethod
    def interrupt(self, reason: str) -> None:
        """Executive may interrupt the cycle at any phase (I-02)."""

    @abstractmethod
    def route_to_llm(self, context: str) -> bool:
        """LLM-free core enforcement: True only if budget allows AND no rule covers it."""


# --------------------------------------------------------------------------
# Learning Policy (I-14) — Learning proposes; does not write memory directly.
# --------------------------------------------------------------------------
class ILearningPolicy(ABC):
    """Strategy for the Learn phase. Proposes Knowledge Proposal -> Policy Check -> Commit."""

    @abstractmethod
    def propose(self, episode_ids: List[str]) -> Optional[Policy]:
        """Return a Policy proposal, or None (do nothing). Confidence+repetition gated."""

    @abstractmethod
    def accepts(self, proposal: Policy) -> bool:
        """Policy Check gate before Commit to Memory (I-14)."""


# -------------------------------------------------------------------------
# Reasoning Engine (ТЗ-RE-01) — parametric engine of the Deliberate phase
# -------------------------------------------------------------------------
class IReasoningEngine(ABC):
    """Reasoning step BEFORE Planning (ADR-054 Deliberate: Reasoning -> Planning -> Decision).

    Reads Intent + WorldState (+ Attention context) and yields ReasoningSteps that
    become candidates for the Planner. Deterministic by default (LLM-free core, I-09);
    an LLM may ADVISE but the step generation stays rule/policy-based. Every step
    carries its own ConfidenceScore + CausalMark (the node's shared clock).
    """

    @abstractmethod
    def reason(self, intent: Intent, world: WorldState,
               attention_context: List[str], budget_tokens: int) -> List["ReasoningStep"]:
        """Return world-aware reasoning steps (candidates for Planning)."""


# -------------------------------------------------------------------------
# World State (I-07) — local node single source of truth.
# -------------------------------------------------------------------------


# --------------------------------------------------------------------------
# World State (I-07) — local node single source of truth.
# --------------------------------------------------------------------------
class IWorldState(ABC):
    """Local node SSOT. All phases read/write through this port (not free mutation).

    `update` accepts a CausalMark (gate C, TZ-015) so facts carry federation-safe
    causality instead of only wall-clock time.
    """

    @abstractmethod
    def update(self, observation: Observation, causal: Optional["CausalMark"] = None) -> WorldState: ...

    @abstractmethod
    def snapshot(self) -> WorldState: ...

    @abstractmethod
    def get(self, key: str) -> Optional[str]: ...


# --------------------------------------------------------------------------
# Layered Memory (I-14) — Learning routes writes by layer (episode vs normative)
# --------------------------------------------------------------------------
class ILayeredMemory(ABC):
    """Two-layer memory (ADR-054 I-14): episode (raw) vs normative (rules/ADR).

    LearningPolicy proposes; memory persists. Write routing by layer is enforced
    here so Learning NEVER writes memory directly (I-14).
    """

    @abstractmethod
    def record_episode(self, episode: "Episode") -> None: ...

    @abstractmethod
    def commit_normative(self, policy: "Policy") -> None: ...

    @abstractmethod
    def get_episodes(self) -> List["Episode"]: ...


# --------------------------------------------------------------------------
# Cognitive Kernel (I-01) — orchestrator wiring the FSM.
# --------------------------------------------------------------------------
class ICognitiveKernel(ABC):
    """Primary invariant: system executes as a Cognitive FSM, not ad-hoc calls (I-01)."""

    @abstractmethod
    def tick(self, intent: Intent) -> CognitiveState:
        """Advance one FSM tick. Returns resulting state. Emits CognitiveEvents (I-17)."""

    @abstractmethod
    def run_system1(self, observation: Observation) -> None:
        """Reactive LLM-free path: Observe->Orient->(rule)->Execute (I-09/I-16)."""

    @abstractmethod
    def on_event(self, handler: Callable[[dict], None]) -> None:
        """Subscribe to CognitiveEvents (replay/audit/federation)."""
