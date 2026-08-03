"""Core Cognitive Domain — first-class frozen entities (ADR-054 I-05/I-12/I-13/I-17/I-18).

K1-compliant: stdlib + contracts ONLY. No service/adapter/runtime imports.
These are the immutable value objects of the Cognitive Kernel. Mutations happen
ONLY through the CognitiveKernel FSM (ADR-054 I-01/I-02), never by direct field edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime as _dt
from enum import Enum
from typing import Dict, List, Optional, Tuple


def _now() -> str:
    return _dt.now().isoformat()


# --------------------------------------------------------------------------
# ConfidenceScore (ADR-055 — unified cross-entity contract, ADR-054 I-12)
# --------------------------------------------------------------------------
class ProvenanceType(str, Enum):
    """Where a confidence number originates (ADR-055)."""
    OBSERVATION = "OBSERVATION"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    RULE_INFERENCE = "RULE_INFERENCE"
    AGGREGATION = "AGGREGATION"


class CalibrationType(str, Enum):
    """Epistemic = 'I don't know, can learn more'; Aleatoric = 'noise of world'."""
    EPISTEMIC = "EPISTEMIC"
    ALEATORIC = "ALEATORIC"


class AggregationRule(str, Enum):
    """How a composite confidence derives from its steps (ADR-055)."""
    MIN = "MIN"
    PRODUCT = "PRODUCT"
    WEIGHTED = "WEIGHTED"


@dataclass(frozen=True)
class ConfidenceScore:
    """Single unified contract carried by EVERY cognitive entity (ADR-054 I-12)."""
    value: float                                   # 0..1
    provenance: ProvenanceType = ProvenanceType.AGGREGATION
    calibration: CalibrationType = CalibrationType.ALEATORIC
    aggregation_rule: Optional[AggregationRule] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"ConfidenceScore.value must be 0..1, got {self.value}")
        if self.aggregation_rule is None and self.provenance is ProvenanceType.AGGREGATION:
            object.__setattr__(self, "aggregation_rule", AggregationRule.WEIGHTED)


def aggregate_confidence(steps: List[ConfidenceScore],
                         rule: Optional[AggregationRule] = None) -> ConfidenceScore:
    """Combine step confidences into a composite (ADR-055).

    - MIN: conservative lower bound (one weak step sinks the plan).
    - PRODUCT: multiplicative (independence assumption).
    - WEIGHTED: depth-weighted average (default), later steps weigh slightly less.
    """
    if not steps:
        return ConfidenceScore(0.0, ProvenanceType.AGGREGATION)
    rule = rule or AggregationRule.WEIGHTED
    vals = [s.value for s in steps]
    if rule is AggregationRule.MIN:
        comp = min(vals)
    elif rule is AggregationRule.PRODUCT:
        import math
        comp = math.prod(vals)
    else:  # WEIGHTED: deeper steps weigh (n - i)/n
        n = len(vals)
        w = [(n - i) / n for i in range(n)]
        comp = sum(v * wi for v, wi in zip(vals, w)) / sum(w)
    return ConfidenceScore(
        round(comp, 4), ProvenanceType.AGGREGATION,
        calibration=CalibrationType.EPISTEMIC, aggregation_rule=rule,
    )


# --------------------------------------------------------------------------
# Provenance (ADR-054 I-13) — every cognitive artifact carries this
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Provenance:
    """Origin trace: who/what produced an artifact (for replay/audit/federation)."""
    source: str                 # observation | agent:<id> | rule:<name> | model:<name>
    actor: str                  # agent_id / 'kernel' / 'system'
    timestamp: str = field(default_factory=_now)


# --------------------------------------------------------------------------
# Cognitive FSM states (ADR-054 I-01) — primary invariant
# --------------------------------------------------------------------------
class CognitiveState(str, Enum):
    """States of the Cognitive Kernel finite-state machine (ADR-054 §4)."""
    IDLE = "IDLE"
    OBSERVE = "OBSERVE"
    ORIENT = "ORIENT"
    DELIBERATE = "DELIBERATE"
    COMMIT = "COMMIT"
    EXECUTE = "EXECUTE"
    EVALUATE = "EVALUATE"
    LEARN = "LEARN"

    @property
    def is_terminal(self) -> bool:
        return self is CognitiveState.IDLE


# --------------------------------------------------------------------------
# Event Semantics (ADR-054 I-17) — reproducible + logged transitions
# --------------------------------------------------------------------------
class CognitiveEventType(str, Enum):
    OBSERVATION_RECEIVED = "ObservationReceived"
    GOAL_CREATED = "GoalCreated"
    GOAL_CANCELLED = "GoalCancelled"
    REASONING_STEP = "ReasoningStep"
    PLAN_GENERATED = "PlanGenerated"
    DECISION_ACCEPTED = "DecisionAccepted"
    DECISION_REJECTED = "DecisionRejected"
    EXECUTION_STARTED = "ExecutionStarted"
    EXECUTION_FINISHED = "ExecutionFinished"
    REFLECTION_COMPLETED = "ReflectionCompleted"
    POLICY_UPDATED = "PolicyUpdated"
    SEMANTIC_CONSOLIDATED = "SemanticConsolidated"
    NORMATIVE_DEPRECATED = "NormativeDeprecated"


# -------------------------------------------------------------------------
# Causal mark (gate C, TZ-015 federation) — Lamport logical clock (ТЗ-CAUSAL-01)
# -------------------------------------------------------------------------
@dataclass(frozen=True)
class CausalMark:
    """Lamport logical clock for causal merge/dedup across federated nodes (ADR-054 I-08/I-17).

    A Lamport clock gives a TOTAL causal order WITHOUT trusting wall-clock time
    (node clocks drift). CRITICAL: the clock is updated on every RECEIVE
    (`receive`) as well as on every local event (`tick`). A per-node seq that is
    only compared across nodes (never advanced on receive) would mean "whoever
    did more operations wins" — which is NOT causal order. This is exactly the
    ТЗ-CAUSAL-01 defect that is closed here.

    Merge rule (LWW): the GREATER mark wins; tiebreak by node_origin so concurrent
    writes to one key converge deterministically on every replica.
    """
    node_origin: str                       # originating node id (tiebreak)
    lamport: int = 0                       # Lamport logical clock value

    def tick(self) -> "CausalMark":
        """Local event: advance own clock by 1."""
        return CausalMark(self.node_origin, self.lamport + 1)

    def receive(self, remote: "CausalMark") -> "CausalMark":
        """Receive event: clock = max(local, remote) + 1 (Lamport rule)."""
        return CausalMark(self.node_origin, max(self.lamport, remote.lamport) + 1)

    def __lt__(self, other: "CausalMark") -> bool:
        # PRIMARY order = lamport (logical clock); node_origin is the deterministic
        # tiebreak so concurrent writes converge identically on every replica.
        return (self.lamport, self.node_origin) < (other.lamport, other.node_origin)


# -------------------------------------------------------------------------
# Shared node Lamport clock (ТЗ-RE-01, flag 1) — ONE clock per node
# -------------------------------------------------------------------------
class NodeLamportClock:
    """Mutable holder for the SINGLE Lamport clock of a node (ТЗ-RE-01 flag 1).

    A node's kernel, world store, reasoning engine and federation service MUST
    share ONE clock so every emitted CausalMark carries the same causal order and
    the same node_origin (= node_id, NOT a hardcoded literal like "kernel").
    Three independent clocks would break causal order and the federation tiebreak.

    K1-compliant: stdlib + contracts only. The holder is intentionally stateful
    (a clock is state); it wraps an immutable CausalMark and advances it via
    `tick` (local event) / `receive` (remote event).
    """
    def __init__(self, node_id: str) -> None:
        self._node_id = node_id
        self._mark = CausalMark(node_id, 0)

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def mark(self) -> "CausalMark":
        return self._mark

    def tick(self) -> "CausalMark":
        """Local event: advance the shared clock by 1, return the new mark."""
        self._mark = CausalMark(self._node_id, self._mark.lamport + 1)
        return self._mark

    def receive(self, remote: "CausalMark") -> "CausalMark":
        """Receive event: clock = max(local, remote) + 1 (Lamport rule)."""
        self._mark = CausalMark(self._node_id, max(self._mark.lamport, remote.lamport) + 1)
        return self._mark


@dataclass(frozen=True)
class CognitiveEvent:
    """Emitted on every FSM transition (I-17). Reuse IEventBus.publish(topic, dict)."""
    type: CognitiveEventType
    ref_id: str                          # related entity id (goal/plan/decision/...)
    provenance: Provenance
    confidence: ConfidenceScore
    timestamp: str = field(default_factory=_now)
    causal: CausalMark = field(default_factory=lambda: CausalMark("local", 0))

    def to_bus(self) -> dict:
        """Convert to IEventBus payload shape (dict, topic = type.value)."""
        return {
            "type": self.type.value,
            "ref_id": self.ref_id,
            "actor": self.provenance.actor,
            "source": self.provenance.source,
            "confidence": self.confidence.value,
            "calibration": self.confidence.calibration.value,
            "provenance_type": self.confidence.provenance.value,
            "timestamp": self.timestamp,
            "causal_node": self.causal.node_origin,
            "causal_lamport": self.causal.lamport,
        }


# --------------------------------------------------------------------------
# First-class domain entities (ADR-054 I-18) — frozen, not dicts
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Intent:
    """Source of all goals (ADR-054 I-04)."""
    id: str
    text: str
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class Goal:
    """A goal derived from an Intent, owned by the kernel."""
    id: str
    intent_id: str
    description: str
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class Plan:
    """A candidate plan produced by the Planner (ADR-054 I-03 — Planner != Decision)."""
    id: str
    goal_id: str
    steps: Tuple[str, ...]               # ordered step ids/descriptions
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class Decision:
    """The ONE chosen plan, selected deterministically by Decision Engine (I-03)."""
    id: str
    goal_id: str
    selected_plan_id: str
    rationale: str                       # expected-utility trace (deterministic)
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class Observation:
    """A fact entering the system (ADR-054 I-07 WorldState update)."""
    id: str
    content: str
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class Episode:
    """A recorded experience (memory record, TZ-017)."""
    id: str
    summary: str
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class SemanticFact:
    """A consolidated semantic fact derived from repeated high-confidence episodes
    (ТЗ-ME-01, ADR-046). Lives in the SOFT semantic layer — never in the HARD layer.

    Confidence is AGGREGATED across the source episodes (ADR-055 aggregate_confidence),
    not a naive max. The CausalMark is taken from the node's shared Lamport clock
    (ТЗ-RE-01 flag 1) so consolidated facts share one causal order.
    """
    id: str
    content: str
    confidence: ConfidenceScore
    causal: CausalMark
    source_episodes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Policy:
    """A normative or soft policy (Normative Memory, I-11/I-19)."""
    id: str
    name: str
    layer: str                          # 'hard' | 'soft'
    body: str
    confidence: ConfidenceScore
    provenance: Provenance
    lifecycle: "PolicyLifecycle" = None  # ACTIVE/DEPRECATED/SUPERSEDED (ТЗ-ME-01)


class PolicyLifecycle(Enum):
    """Lifecycle state of a normative/soft policy (ТЗ-ME-01, ADR-046).

    ACTIVE — currently in force. DEPRECATED — no longer recommended (low confidence /
    outdated) but kept for traceability. SUPERSEDED — replaced by a newer policy
    (superseded_by records the successor id). Only SOFT policies ever change lifecycle;
    HARD constraints are immutable (O1 — Self-Evolving guard).
    """
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class ExecutionOutcome:
    """Outcome of an executed decision — feedback signal for Reflection (ТЗ-RF-01).

    Outcome is a PROXY (ФЛАГ 1): success = decision was accepted/executed, utility =
    decision confidence (or predicted utility). Real environment feedback (RL/reward)
    is future. Reflection uses this to drive outcome-based consolidation/deprecation
    instead of merely repeating intent text.
    """
    episode_id: str
    success: bool
    utility: float
    confidence: ConfidenceScore
    causal: CausalMark


@dataclass(frozen=True)
class ReflectionReport:
    """Reflection Engine output (ТЗ-RF-01). Analytic part of Self-Evolving: proposes
    (does NOT write) evolution of the SOFT layer from accumulated experience.

    Carries the node's CausalMark (ТЗ-RE-01 flag 1) so the report is causally ordered.
    Every candidate carries a ConfidenceScore. Evolution targets only the SOFT layer;
    HARD is immutable (O1 — Self-Evolving guard, enforced at commit time in Memory
    Evolution / kernel).
    """
    consolidation_candidates: "Tuple[SemanticFact, ...]" = ()
    deprecation_candidates: "Tuple[str, ...]" = ()   # episode/policy ids to deprecate
    policy_suggestions: "Tuple[Policy, ...]" = ()     # SOFT-only policy proposals
    insights: "Tuple[str, ...]" = ()
    confidence: ConfidenceScore = None
    causal: CausalMark = None


@dataclass(frozen=True)
class Action:
    """An executable action routed to an agent/model (I-10 Contract Boundary)."""
    id: str
    kind: str                           # 'agent_call' | 'llm_call' | 'rule'
    payload: str
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class Skill:
    """A reusable capability (Marketplace/TZ-021)."""
    id: str
    name: str
    confidence: ConfidenceScore
    provenance: Provenance


@dataclass(frozen=True)
class ReasoningStep:
    """One deterministic reasoning step in the Deliberate phase (ТЗ-RE-01).

    A reasoning step reads WorldState + Intent (via the engine) and produces a
    candidate for Planning. Each step carries a ConfidenceScore (ADR-054 I-12) and
    a CausalMark from the node's shared clock (ТЗ-CAUSAL-01 / ТЗ-RE-01 flag 1) so
    reasoning is causally ordered and world-aware by construction.
    """
    id: str
    goal_id: str
    description: str                       # what the step concluded / which candidate
    based_on_facts: Tuple[str, ...] = ()   # world keys this step read (world-awareness)
    confidence: ConfidenceScore = field(
        default_factory=lambda: ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE)
    )
    causal: CausalMark = field(default_factory=lambda: CausalMark("local", 0))


@dataclass(frozen=True)
class PredictedState:
    """A predicted future world state projected by the World Model (ТЗ-WM-01).

    The World Model is an ADVISOR over WorldState (ADR-047): it projects the outcome
    of an action / plan horizon steps ahead. Confidence MUST fall with the horizon
    (further projection = more uncertain) — that is the whole point of prediction.
    The CausalMark is taken from the node's shared Lamport clock (ТЗ-RE-01 flag 1),
    so predicted states share one causal order with kernel events + world facts.
    """
    id: str
    horizon: int                               # how many steps ahead this projection is
    projected_facts: Dict[str, str] = field(default_factory=dict)
    confidence: ConfidenceScore = field(
        default_factory=lambda: ConfidenceScore(0.5, ProvenanceType.RULE_INFERENCE)
    )
    causal: CausalMark = field(default_factory=lambda: CausalMark("local", 0))


@dataclass(frozen=True)
class WorldState:
    """Local node single source of truth snapshot (ADR-054 I-07).

    The live store is behind IWorldState port; this is the immutable projection
    the FSM reads/writes through transitions. `facts_meta` carries the CAUSAL mark
    per fact (gate C, TZ-015) so federated merge/dedup is well-defined without
    trusting wall-clock time.
    """
    node_id: str
    facts: Dict[str, str] = field(default_factory=dict)
    facts_meta: Dict[str, CausalMark] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now)
    confidence: ConfidenceScore = field(
        default_factory=lambda: ConfidenceScore(1.0, ProvenanceType.OBSERVATION)
    )
