"""Tenant memory/knowledge isolation helpers (TZ-MULTI-001 WP-05, ADR-035 R4).

K1-compliant: contracts only. These helpers apply the tenant namespace OUTSIDE
the Memory Platform / Knowledge Graph (which are NOT modified, R3 mitigation):
callers scope keys/queries via scope_key() before touching storage.
"""
from __future__ import annotations

from contracts.tenant import ITenantIsolator, TenantId


class TenantMemoryNamespace:
    """Scope memory node/record keys per tenant (ADR-035 R4)."""

    def __init__(self, isolator: ITenantIsolator) -> None:
        self._iso = isolator

    def scope_key(self, tenant_id: str, key: str) -> str:
        return self._iso.scope_key(tenant_id, key)

    def node_id(self, tenant_id: str, node_label: str) -> str:
        return self._iso.scope_key(tenant_id, f"memory:{node_label}")


class TenantRAGFilter:
    """Filter RAG/vector queries by tenant (ADR-035 R4, integration w/ ADR-025)."""

    def __init__(self, isolator: ITenantIsolator) -> None:
        self._iso = isolator

    def filter_query(self, tenant_id: str, query: str) -> str:
        """Tag a RAG query with the tenant scope prefix (informational)."""
        TenantId(tenant_id)
        return f"[tenant:{tenant_id}] {query}"

    def owns(self, tenant_id: str, stored_key: str) -> bool:
        """True if a stored record belongs to this tenant (scope_key prefix)."""
        return stored_key.startswith(f"tenant:{tenant_id}:")


class TenantKnowledgeBoundary:
    """Check graph-traversal / knowledge access across tenant (ADR-035 R6)."""

    def __init__(self, isolator: ITenantIsolator) -> None:
        self._iso = isolator

    def can_read(self, src_tenant: str, node_tenant: str) -> bool:
        """Caller (src) may read a node owned by node_tenant?"""
        return self._iso.check_boundary(src_tenant, node_tenant)

    def can_write(self, src_tenant: str, dst_tenant: str) -> bool:
        return self._iso.check_boundary(src_tenant, dst_tenant)
