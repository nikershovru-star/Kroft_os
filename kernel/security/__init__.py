"""kernel/security — capability boundary core (TZ-SEC-001).

K1-compliant: this package imports ONLY contracts + stdlib. It provides the
clean authorization/sandbox/approval logic. Heavy IO (secret storage, audit
sink, terminal) is implemented in services/security/* behind contracts/security.
"""
from .approval_manager import ApprovalManager
from .capability_manager import CapabilityManager
from .policy_engine import AuthorizationEngine
from .sandbox import FileSandbox

__all__ = [
    "ApprovalManager",
    "CapabilityManager",
    "AuthorizationEngine",
    "FileSandbox",
]
