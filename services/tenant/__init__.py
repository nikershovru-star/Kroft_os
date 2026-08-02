"""services/tenant — tenant IO layer (TZ-MULTI-001 WP-03, ADR-035).

Implements contracts.tenant ports. K1-compliant: imports ONLY contracts
(+ stdlib). Never imports kernel. Persistence + approval wiring live here.
"""
from .isolator import TenantIsolator
from .tenant_manager import InMemoryTenantManager, JsonlTenantManager

__all__ = ["InMemoryTenantManager", "JsonlTenantManager", "TenantIsolator"]
