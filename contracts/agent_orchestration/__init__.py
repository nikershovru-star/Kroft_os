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
from typing import Dict, List, Optional

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
    def spawn(self, agent_id: str, tenant_id: str, role: str, goal: str) -> AgentState: ...

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
                    required_capabilities: List[str]) -> List[AgentResult]: ...

    @abstractmethod
    def get_pool(self, tenant_id: str) -> List[str]: ...


class IAgentMessenger(ABC):
    """Inter-agent messaging port — EventBus only (WP-04, K6)."""

    @abstractmethod
    def send(self, msg: AgentMessage) -> bool: ...

    @abstractmethod
    def receive(self, agent_id: str) -> List[AgentMessage]: ...


class ISelfAnalyzer(ABC):
    """Runtime self-analysis port (WP-05, K8 meta-layer)."""

    @abstractmethod
    def health_check(self) -> HealthReport: ...

    @abstractmethod
    def detect_drift(self) -> List[DriftRecord]: ...
