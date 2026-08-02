"""services/security — heavy IO security implementations (TZ-SEC-001).

Implements contracts/security ports: SecretManager, AuditLogger, TerminalExecutor.
Clean kernel logic (CapabilityManager, AuthorizationEngine, ApprovalManager,
FileSandbox) lives in kernel/security/ (contracts-only). This package depends
on contracts/security only (services never import kernel per K1).
"""
from .audit_logger import AuditLogger, make_record
from .secret_manager import SecretManager
from .terminal_executor import TerminalExecutor

__all__ = ["AuditLogger", "make_record", "SecretManager", "TerminalExecutor"]
