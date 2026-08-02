"""Security ports (TZ-SEC-001 WP-01/03/04/05/07/08).

K1-compliant: this module imports ONLY stdlib. Kernel-internal security logic
(kernel/security/*) depends on these ports; heavy IO implementations live in
services/security/* (also via these ports). Never import services/ here.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# --------------------------------------------------------------------------
# Capability model (ADR-033)
# --------------------------------------------------------------------------
class CapabilityCategory(str, Enum):
    TOOL = "Tool"
    FILESYSTEM = "Filesystem"
    NETWORK = "Network"
    MEMORY = "Memory"
    RAG = "RAG"
    GRAPH = "Graph"
    PLANNER = "Planner"
    SHELL = "Shell"
    PYTHON = "Python"
    GIT = "Git"
    SECRETS = "Secrets"
    ADMIN = "Admin"


@dataclass(frozen=True)
class Capability:
    """A single permission, e.g. Filesystem.Write, Memory.Store, Shell.Execute."""

    category: CapabilityCategory
    operation: str = "*"  # Read / Write / Execute / Store / Delete ...

    @property
    def id(self) -> str:
        return f"{self.category.value}.{self.operation}"

    @classmethod
    def parse(cls, spec: str) -> "Capability":
        if "." in spec:
            cat, op = spec.split(".", 1)
        else:
            cat, op = spec, "*"
        return cls(CapabilityCategory(cat), op)

    def matches(self, other: "Capability") -> bool:
        """other is granted if same category and (op wildcard or exact)."""
        if self.category != other.category:
            return False
        return self.operation == "*" or self.operation == other.operation


class Role(str, Enum):
    ARCHITECT = "Architect"
    RESEARCHER = "Researcher"
    CODER = "Coder"
    ANALYST = "Analyst"
    REVIEWER = "Reviewer"
    MEMORY_AGENT = "MemoryAgent"
    PLANNER = "Planner"
    OPERATOR = "Operator"
    ADMIN = "Admin"


# --------------------------------------------------------------------------
# Context & decision types
# --------------------------------------------------------------------------
@dataclass
class CapabilityContext:
    """Who is calling and on what (ADR-033)."""

    agent_id: str
    role: Role
    granted: List[Capability] = field(default_factory=list)


class ICapabilityContext(abc.ABC):
    """Port for the authorization context (ADR-033 WP-01)."""

    agent_id: str
    role: Role
    granted: List[Capability]

    @abc.abstractmethod
    def has(self, cap: Capability) -> bool: ...


@dataclass
class AuthDecision:
    allowed: bool
    capability: Optional[Capability] = None
    reason: str = ""
    requires_approval: bool = False  # dangerous action -> WAIT_APPROVAL

    @classmethod
    def allow(cls, capability: Capability) -> "AuthDecision":
        return cls(allowed=True, capability=capability)

    @classmethod
    def deny(cls, capability: Capability, reason: str) -> "AuthDecision":
        return cls(allowed=False, capability=capability, reason=reason)

    @classmethod
    def needs_approval(cls, capability: Capability) -> "AuthDecision":
        return cls(allowed=False, capability=capability,
                   reason="dangerous action requires human approval",
                   requires_approval=True)


# --------------------------------------------------------------------------
# Ports (Protocols)
# --------------------------------------------------------------------------
class ICapabilityPolicy(abc.ABC):
    """A single RBAC/policy rule (ADR-033)."""

    @abc.abstractmethod
    def evaluate(self, ctx: CapabilityContext, required: Capability) -> AuthDecision: ...


class ICapabilityManager(abc.ABC):
    """Resolves an agent's granted capabilities and answers authorization."""

    @abc.abstractmethod
    def context_for(self, agent_id: str, role: Role) -> CapabilityContext: ...

    @abc.abstractmethod
    def authorize(self, ctx: CapabilityContext, required: Capability) -> AuthDecision: ...

    @abc.abstractmethod
    def register_role(self, role: Role, capabilities: List[Capability]) -> None: ...


class IPolicyEngine(abc.ABC):
    """Authorization orchestrator: Agent -> Role -> Capability -> Tool -> Exec."""

    @abc.abstractmethod
    def authorize(self, agent_id: str, role: Role, required: Capability) -> AuthDecision: ...

    @abc.abstractmethod
    def authorize_tool(self, agent_id: str, role: Role, tool_name: str,
                       required: List[str]) -> AuthDecision: ...


# --------------------------------------------------------------------------
# Secret manager port (ADR-032 WP-04)
# --------------------------------------------------------------------------
class ISecretManager(abc.ABC):
    @abc.abstractmethod
    def get(self, key: str) -> str:
        """Returns the secret value (masked in logs/audit automatically)."""

    @abc.abstractmethod
    def has(self, key: str) -> bool: ...

    @abc.abstractmethod
    def mask(self, value: str) -> str:
        """Mask a secret for display (e.g. sk-1234....abcd)."""


# --------------------------------------------------------------------------
# Audit logger port (ADR-032 WP-07)
# --------------------------------------------------------------------------
@dataclass
class AuditRecord:
    timestamp: str
    agent_id: str
    tool: str
    arguments: str
    result: str
    duration_ms: float
    status: str  # ok | denied | error | approval_required


class IAuditLogger(abc.ABC):
    @abc.abstractmethod
    def log(self, record: AuditRecord) -> None: ...

    @abc.abstractmethod
    def tail(self, limit: int = 100) -> List[AuditRecord]: ...


# --------------------------------------------------------------------------
# Approval manager port (ADR-034)
# --------------------------------------------------------------------------
class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


@dataclass
class ApprovalRequest:
    agent_id: str
    action: str
    arguments: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    decision_reason: str = ""


class IApprovalManager(abc.ABC):
    @abc.abstractmethod
    def request(self, agent_id: str, action: str, arguments: str) -> ApprovalRequest: ...

    @abc.abstractmethod
    def decide(self, request_id: str, approve: bool, reason: str = "") -> ApprovalRequest: ...

    @abc.abstractmethod
    def wait(self, request_id: str, timeout: float = 0.0) -> ApprovalRequest:
        """Block until a decision is made (timeout=0 -> async/non-blocking)."""


# --------------------------------------------------------------------------
# Terminal executor port (ADR-032 WP-05)
# --------------------------------------------------------------------------
class ITerminalExecutor(abc.ABC):
    @abc.abstractmethod
    def execute(self, command: str, timeout: float = 30.0) -> "TerminalResult": ...


@dataclass
class TerminalResult:
    returncode: int
    stdout: str
    stderr: str
    blocked: bool = False
    block_reason: str = ""
