"""Tenant isolator implementation (TZ-MULTI-001 WP-03/R6, ADR-035).

K1-compliant: contracts only. Enforces the cross-tenant boundary and provides
tenant-scoped path/key helpers used by FileSandbox, Memory, Secrets.
"""
from __future__ import annotations

from contracts.tenant import ITenantIsolator, TenantId


class TenantIsolator(ITenantIsolator):
    """Cross-tenant boundary + scoping helpers (ADR-035 R6, K6)."""

    # Tenants that may span/observe others (global admin scope). Empty by default.
    def __init__(self, global_tenants: frozenset = frozenset()) -> None:
        self._global = global_tenants

    def check_boundary(self, src_tenant: str, dst_tenant: str) -> bool:
        TenantId(src_tenant)
        TenantId(dst_tenant)
        if src_tenant == dst_tenant:
            return True
        # Global tenants (e.g. admin) may cross; default tenant cannot.
        return src_tenant in self._global

    def namespace_path(self, tenant_id: str, relative_path: str) -> str:
        TenantId(tenant_id)
        rel = relative_path.lstrip("/\\")
        return f"workspace/{tenant_id}/{rel}"

    def scope_key(self, tenant_id: str, key: str) -> str:
        TenantId(tenant_id)
        return f"tenant:{tenant_id}:{key}"
