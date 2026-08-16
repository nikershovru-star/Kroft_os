"""Agent orchestration ports & value objects (TZ-AGENT-001, RFC-009/ADR-037).

K1-compliant: stdlib + contracts only. No service-layer imports.
The orchestration layer is a KROFT-native component that reuses the existing
substrate (CapabilityManager, TenantIsolator, IEventBus, Knowledge Graph).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime as _dt
from enum import Enum
from typing import Dict, List, Optional, Tuple

from contracts.i_agent_platform import AgentResult  # reuse existing frozen VO
from contracts.tenant import TenantId


class AgentState(str, Enum):
    """Lifecycle states of an agent (R1, ADR-037 §2)."""

    SPAWNED = "SPAWNED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    STALE = "STALE"
    TERMINATED = "TERMINATED"

    @property
    def is_terminal(self) -> bool:
        return self is AgentState.TERMINATED


class AgentDivision(str, Enum):
    """Business-domain taxonomy of agents (ADR-033, orthogonal to security Role).

    Source of truth = KROFT_OS contracts (NOT the external agency-agents repo).
    A division is the business domain an agent operates in; it is independent of
    the agent's privileges (Role) or fine-grained skills (Capability).
    """

    ACADEMIC = "academic"
    DESIGN = "design"
    ENGINEERING = "engineering"
    FINANCE = "finance"
    GAME_DEV = "game-development"
    GIS = "gis"
    HEALTHCARE = "healthcare"
    MARKETING = "marketing"
    PAID_MEDIA = "paid-media"
    PRODUCT = "product"
    PROJECT_MGMT = "project-management"
    SALES = "sales"
    SECURITY = "security"
    SPATIAL = "spatial-computing"
    SPECIALIZED = "specialized"
    SUPPORT = "support"
    TESTING = "testing"


def _now() -> str:
    return _dt.now().isoformat()


@dataclass
class AgentLifecycleEvent:
    """Traceable transition record (K4, ADR-037 §2)."""

    agent_id: str
    from_state: AgentState
    to_state: AgentState
    timestamp: str = field(default_factory=_now)
    reason: str = ""


@dataclass
class AgentMessage:
    """Inter-agent message carried over the EventBus (R4, K6)."""

    id: str
    sender_id: str
    recipient_id: str
    tenant_id: str
    payload: str
    capability_required: str
    timestamp: str = field(default_factory=_now)


@dataclass
class HealthReport:
    """Result of a runtime health check (R6, WP-05)."""

    status: str  # green | yellow | red
    agents: Dict[str, str] = field(default_factory=dict)  # agent_id -> state
    drifts: List["DriftRecord"] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)

    @property
    def is_healthy(self) -> bool:
        return self.status == "green"


@dataclass
class DriftRecord:
    """Architecture drift detected by SelfAnalyzer (R7, K8)."""

    file: str
    line: int
    rule: str
    actual_import: str


class IAgentLifecycle(ABC):
    """Agent lifecycle state machine port (WP-02)."""

    @abstractmethod
    def spawn(self, agent_id: str, tenant_id: str, role: str, goal: str,
              division: Optional["AgentDivision"] = None) -> AgentState: ...

    @abstractmethod
    def transition(self, agent_id: str, to_state: AgentState, reason: str) -> AgentLifecycleEvent: ...

    @abstractmethod
    def terminate(self, agent_id: str, reason: str) -> AgentLifecycleEvent: ...

    @abstractmethod
    def get_state(self, agent_id: str) -> Optional[AgentState]: ...


class IAgentOrchestrator(ABC):
    """Multi-agent goal distribution port (WP-03)."""

    @abstractmethod
    def submit_goal(self, tenant_id: str, goal: str,
                    required_capabilities: List[str],
                    workflow: Optional["AgentWorkflow"] = None) -> List[AgentResult]: ...

    @abstractmethod
    def get_pool(self, tenant_id: str) -> List[str]: ...


class IAgentMessenger(ABC):
    """Inter-agent messaging port — EventBus only (WP-04, K6)."""

    @abstractmethod
    def send(self, msg: AgentMessage) -> bool: ...

    @abstractmethod
    def receive(self, agent_id: str) -> List[AgentMessage]: ...


class IAgentRecovery(ABC):
    """Agent recovery authority port (Wave 2 WP-10, ADR-038, K6).

    The Supervisor drives agent recovery ONLY through this port — never by
    importing services/agent_orchestration/healing.py directly (K6).
    """

    @abstractmethod
    def restart_agent(self, agent_id: str) -> bool: ...

    @abstractmethod
    def quarantine_agent(self, agent_id: str) -> bool: ...

    @abstractmethod
    def get_agent_health(self, agent_id: str) -> Optional[AgentState]: ...


class ISelfAnalyzer(ABC):
    """Runtime self-analysis port (WP-05, K8 meta-layer)."""

    @abstractmethod
    def health_check(self) -> HealthReport: ...

    @abstractmethod
    def detect_drift(self) -> List[DriftRecord]: ...


# ── ADR-033: declarative multi-agent workflow + graph-backed handoff ──────────
@dataclass(frozen=True)
class WorkflowStep:
    """One stage of an AgentWorkflow.

    `agent_division` selects which business-domain agent runs it;
    `required_capabilities` are matched against the capability registry;
    `handoff_key` links this step's output to the next via AgentMemoryHandoff.
    """

    agent_division: AgentDivision
    required_capabilities: List[str]
    handoff_key: str
    depends_on: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentWorkflow:
    """Declarative multi-agent pipeline (ADR-033).

    Orthogonal to the generic `contracts.i_workflow.Workflow` — this VO is
    orchestration-specific (division + capability + handoff per step).
    """

    id: str
    name: str
    steps: Tuple[WorkflowStep, ...]


@dataclass(frozen=True)
class AgentMemoryHandoff:
    """Pointer to a deliverable produced by one agent, consumed by the next.

    Backed by the EXISTING Knowledge Graph as a workflow-artifact node
    (meta["type"] == "handoff", NOT a trusted knowledge FACT) + meta, NOT
    an external MCP server. `payload_ref` is the graph node id holding the data.
    """

    workflow_id: str
    step_id: str
    producer_agent_id: str
    consumer_division: AgentDivision
    payload_ref: str


class IAgentMemoryHandoff(ABC):
    """Persistent agent-to-agent handoff over the existing Knowledge Graph (ADR-033).

    Implementations write the deliverable as a graph node (meta["type"] ==
    "handoff" — a workflow artifact, NOT a trusted knowledge FACT) with
    meta.workflow_id / meta.step_id / meta.division via IGraphBuilder, and read
    it back via IGraphQuery.nodes_by_metadata — reusing the Multi-Resolution API
    (no new query methods).
    """

    @abstractmethod
    def publish_handoff(self, ho: AgentMemoryHandoff, payload: dict) -> str:
        """Store `payload` as a graph node; return its node id (payload_ref)."""

    @abstractmethod
    def consume_handoff(self, workflow_id: str,
                        consumer_division: AgentDivision) -> List[dict]:
        """Return payloads for `workflow_id` scoped to `consumer_division`."""
