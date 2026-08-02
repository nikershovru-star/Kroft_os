"""Tenant context provider (TZ-MULTI-001 WP-02, ADR-035).

Thread/async-safe carrier of the current tenant. Backed by a ContextVar
(async-safe) with a thread-local fallback for sync callers. Composition/CLI set
the current context; kernel/services read it. Fail-closed: get_current() never
returns None — it returns DefaultTenantContext ("default") when unset (R9).
"""
from __future__ import annotations

import threading
from contextvars import ContextVar
from typing import Optional

from contracts.tenant import ITenantContext, TenantId

from .context import TenantContext

_var: ContextVar[Optional[ITenantContext]] = ContextVar("kroft_tenant", default=None)
_local = threading.local()


class TenantContextProvider:
    """Holds the current tenant for the running thread/async task (ADR-035 WP-02)."""

    @classmethod
    def set_current(cls, ctx: ITenantContext) -> None:
        _var.set(ctx)
        _local.ctx = ctx

    @classmethod
    def get_current(cls) -> ITenantContext:
        ctx = _var.get()
        if ctx is None:
            ctx = getattr(_local, "ctx", None)
        if ctx is None:
            ctx = DefaultTenantContext()
        return ctx

    @classmethod
    def get_current_tenant_id(cls) -> str:
        return cls.get_current().tenant_id

    @classmethod
    def clear(cls) -> None:
        _var.set(None)
        if hasattr(_local, "ctx"):
            _local.ctx = None


class DefaultTenantContext(TenantContext):
    """Fallback context: tenant "default" (backward compat, R9)."""

    def __init__(self) -> None:
        super().__init__(tenant_id="default", agent_id="default")
