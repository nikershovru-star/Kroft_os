"""kernel/tenant — tenant context core (TZ-MULTI-001, ADR-035).

K1-compliant: imports ONLY contracts.tenant + stdlib. Provides the explicit
tenant carrier (TenantContext, TenantContextProvider, DefaultTenantContext).
Heavy IO (tenant persistence, approval) lives in services/tenant/ (K1 boundary).
"""
from .context import TenantContext
from .isolation import TenantKnowledgeBoundary, TenantMemoryNamespace, TenantRAGFilter
from .provider import DefaultTenantContext, TenantContextProvider

__all__ = [
    "TenantContext",
    "DefaultTenantContext",
    "TenantContextProvider",
    "TenantMemoryNamespace",
    "TenantRAGFilter",
    "TenantKnowledgeBoundary",
]
