"""Runtime tenant context (TZ-MULTI-001 WP-02, ADR-035).

K1-compliant: imports ONLY contracts.tenant + stdlib. Provides an explicit,
thread/async-safe current-tenant carrier. Never uses os.environ or a global
variable (K1/K8). Default fallback tenant is "default" for backward compat (R9).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from contracts.tenant import ITenantContext, TenantId


@dataclass
class TenantContext(ITenantContext):
    """Concrete tenant context (ADR-035 WP-02)."""

    tenant_id: str
    agent_id: str = "unknown"
    metadata: Dict[str, str] = field(default_factory=dict)

    def tenant(self) -> TenantId:
        return TenantId(self.tenant_id)

    def has_metadata(self, key: str) -> bool:
        return key in self.metadata

    @classmethod
    def default(cls) -> "TenantContext":
        return cls(tenant_id="default", agent_id="default")
