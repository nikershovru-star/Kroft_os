"""Tenant manager implementations (TZ-MULTI-001 WP-03, ADR-035).

K1-compliant for services: imports ONLY contracts.tenant + stdlib. Heavy IO
(persistence, approval wiring) lives here — never in kernel. create()/delete()
delegate to an injected ApprovalManager when provided (K5); without one they
fail closed (deny). Soft-delete keeps an audit trail (R7, K4).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from contracts.tenant import ITenantManager, TenantId, TenantRecord

try:  # approval port is defined in contracts.security (K1: services may import contracts)
    from contracts.security import IApprovalManager, ApprovalStatus
except Exception:  # pragma: no cover - port always present
    IApprovalManager = None
    ApprovalStatus = None


class InMemoryTenantManager(ITenantManager):
    """Default thread-safe tenant store (ADR-035 WP-03)."""

    def __init__(self, approval: "Optional[IApprovalManager]" = None,
                 persistence_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._store: Dict[str, TenantRecord] = {}
        self._approval = approval
        self._persistence_path = persistence_path
        if persistence_path:
            self._load()

    # --- approval helper (K5) ---
    def _require_approval(self, action: str, target: str) -> None:
        if self._approval is None:
            # Fail closed: no approval channel -> deny.
            raise PermissionError(
                f"tenant {action} requires human approval (K5) but no ApprovalManager wired"
            )
        req = self._approval.request("tenant-admin", action, target)
        # In a real system this blocks on human decision. Here we surface the
        # pending request; caller must decide() before the op proceeds.
        if req.status != ApprovalStatus.APPROVED:
            raise PermissionError(
                f"tenant {action} pending approval (req={req.id}); denied until human approves"
            )

    def create(self, tenant_id: str, created_by: str,
               metadata: Optional[Dict[str, str]] = None) -> TenantRecord:
        TenantId(tenant_id)  # validate (fail-closed on bad id)
        self._require_approval("create_tenant", tenant_id)
        with self._lock:
            if tenant_id in self._store and not self._store[tenant_id].deleted:
                raise ValueError(f"tenant {tenant_id} already exists")
            rec = TenantRecord(
                tenant_id=tenant_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                created_by=created_by,
                metadata=dict(metadata or {}),
            )
            self._store[tenant_id] = rec
            self._save()
            return rec

    def get(self, tenant_id: str) -> Optional[TenantRecord]:
        with self._lock:
            rec = self._store.get(tenant_id)
            return rec if (rec and not rec.deleted) else None

    def exists(self, tenant_id: str) -> bool:
        with self._lock:
            rec = self._store.get(tenant_id)
            return rec is not None and not rec.deleted

    def list(self) -> List[TenantRecord]:
        with self._lock:
            return [r for r in self._store.values() if not r.deleted]

    def delete(self, tenant_id: str) -> bool:
        TenantId(tenant_id)
        self._require_approval("delete_tenant", tenant_id)
        with self._lock:
            rec = self._store.get(tenant_id)
            if rec is None or rec.deleted:
                return False
            rec.deleted = True  # soft delete (R7, K4 audit trail)
            self._save()
            return True

    def set_metadata(self, tenant_id: str, key: str, value: str) -> None:
        with self._lock:
            rec = self._store.get(tenant_id)
            if rec is None or rec.deleted:
                raise KeyError(tenant_id)
            rec.metadata[key] = value
            self._save()

    # --- optional JSONL persistence ---
    def _load(self) -> None:
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    rec = TenantRecord(
                        tenant_id=d["tenant_id"], created_at=d["created_at"],
                        created_by=d["created_by"], metadata=d.get("metadata", {}),
                        deleted=d.get("deleted", False),
                    )
                    self._store[rec.tenant_id] = rec
        except FileNotFoundError:
            pass

    def _save(self) -> None:
        if not self._persistence_path:
            return
        tmp = self._persistence_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for rec in self._store.values():
                fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        import os
        os.replace(tmp, self._persistence_path)


class JsonlTenantManager(InMemoryTenantManager):
    """Alias for the append-friendly JSONL-backed manager (ADR-035 WP-03 Q1)."""

    def append_event(self, event: Dict[str, object]) -> None:
        if not self._persistence_path:
            return
        with open(self._persistence_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
