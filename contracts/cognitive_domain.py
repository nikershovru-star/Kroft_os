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
    PLAN_GENERATED = "PlanGenerated"
    DECISION_ACCEPTED = "DecisionAccepted"
    DECISION_REJECTED = "DecisionRejected"
    EXECUTION_STARTED = "ExecutionStarted"
    EXECUTION_FINISHED = "ExecutionFinished"
    REFLECTION_COMPLETED = "ReflectionCompleted"
    POLICY_UPDATED = "PolicyUpdated"


@dataclass(frozen=True)
class CognitiveEvent:
    """Emitted on every FSM transition (I-17). Reuse IEventBus.publish(topic, dict)."""
    type: CognitiveEventType
    ref_id: str                          # related entity id (goal/plan/decision/...)
    provenance: Provenance
    confidence: ConfidenceScore
    timestamp: str = field(default_factory=_now)

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
class Policy:
    """A normative or soft policy (Normative Memory, I-11/I-19)."""
    id: str
    name: str
    layer: str                          # 'hard' | 'soft'
    body: str
    confidence: ConfidenceScore
    provenance: Provenance


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
class WorldState:
    """Local node single source of truth snapshot (ADR-054 I-07).

    The live store is behind IWorldState port; this is the immutable projection
    the FSM reads/writes through transitions.
    """
    node_id: str
    facts: Dict[str, str] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now)
    confidence: ConfidenceScore = field(
        default_factory=lambda: ConfidenceScore(1.0, ProvenanceType.OBSERVATION)
    )
