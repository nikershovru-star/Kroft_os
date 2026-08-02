"""Tenant isolation ports (TZ-MULTI-001 WP-01, ADR-035).

K1-compliant: this module imports ONLY stdlib. The tenant model is the second
axis of isolation (besides capability). It flows explicitly through ports — never
via os.environ or a global variable (K1/K8).
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

_TENANT_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


class TenantId:
    """Value object for a tenant identifier (ADR-035 R1).

    Validated against ``[a-z0-9_-]{1,32}``. Construction fails closed on
    invalid input.
    """

    __slots__ = ("_id",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not _TENANT_RE.match(value):
            raise ValueError(
                f"invalid tenant_id {value!r}: must match [a-z0-9_-]{{1,32}}"
            )
        object.__setattr__(self, "_id", value)

    @property
    def value(self) -> str:
        return self._id

    @classmethod
    def default(cls) -> "TenantId":
        return cls("default")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TenantId) and other._id == self._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"TenantId({self._id!r})"


class ITenantContext(ABC):
    """Port: who is calling and in which tenant (ADR-035 WP-01)."""

    tenant_id: str
    agent_id: str
    metadata: Dict[str, str]

    @abstractmethod
    def tenant(self) -> TenantId: ...

    @abstractmethod
    def has_metadata(self, key: str) -> bool: ...


class ITenantManager(ABC):
    """Port: lifecycle of tenants (ADR-035 WP-01, R7 K5)."""

    @abstractmethod
    def create(self, tenant_id: str, created_by: str,
               metadata: Optional[Dict[str, str]] = None) -> "TenantRecord": ...

    @abstractmethod
    def get(self, tenant_id: str) -> Optional["TenantRecord"]: ...

    @abstractmethod
    def exists(self, tenant_id: str) -> bool: ...

    @abstractmethod
    def list(self) -> List["TenantRecord"]: ...

    @abstractmethod
    def delete(self, tenant_id: str) -> bool: ...

    @abstractmethod
    def set_metadata(self, tenant_id: str, key: str, value: str) -> None: ...


class ITenantIsolator(ABC):
    """Port: cross-tenant boundary checks (ADR-035 R6, K6)."""

    @abstractmethod
    def check_boundary(self, src_tenant: str, dst_tenant: str) -> bool:
        """Return True if src may access dst (same tenant or explicit allow)."""

    @abstractmethod
    def namespace_path(self, tenant_id: str, relative_path: str) -> str:
        """Resolve a tenant-scoped absolute path (e.g. workspace/{t}/rel)."""

    @abstractmethod
    def scope_key(self, tenant_id: str, key: str) -> str:
        """Scope a storage/memory key: ``tenant:{t}:{key}``."""


@dataclass
class TenantRecord:
    """Persisted tenant record (ADR-035 WP-03)."""

    tenant_id: str
    created_at: str
    created_by: str
    metadata: Dict[str, str] = field(default_factory=dict)
    deleted: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "metadata": dict(self.metadata),
            "deleted": self.deleted,
        }
