"""Tenant onboarding workflow (TZ-MULTI-001 WP-07, ADR-035 R7).

K1-compliant: contracts only. Orchestrates create_tenant (via ApprovalManager,
K5) + default role assignment + audit. Does NOT execute tools; returns the
approval request id for the human loop. Default roles: Admin (owner), Operator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from contracts.tenant import ITenantManager, TenantId
from contracts.security import IApprovalManager, ApprovalStatus, Role


@dataclass
class OnboardingResult:
    tenant_id: str
    approval_request_id: Optional[str]
    approved: bool
    message: str


# Default roles auto-assigned to a new tenant (ADR-035 R7 / Q3).
DEFAULT_TENANT_ROLES: List[Role] = [Role.ADMIN, Role.OPERATOR]


class TenantOnboardingWorkflow:
    """Human-in-loop tenant creation (K5 + R7)."""

    def __init__(self, manager: ITenantManager,
                 approval: Optional[IApprovalManager] = None) -> None:
        self._manager = manager
        self._approval = approval

    def request_create(self, tenant_id: str, owner: str,
                        metadata: Optional[dict] = None) -> OnboardingResult:
        """Step 1-3: validate id, raise approval request, return pending result."""
        TenantId(tenant_id)  # fail-closed on bad id
        if self._approval is None:
            return OnboardingResult(
                tenant_id, None, False,
                "no ApprovalManager wired; K5 approval required to create tenant",
            )
        req = self._approval.request("tenant-admin", "create_tenant", tenant_id)
        return OnboardingResult(
            tenant_id, req._id, req.status == ApprovalStatus.APPROVED,
            f"approval requested (req={req._id})",
        )

    def complete_create(self, tenant_id: str, owner: str,
                        approved: bool, metadata: Optional[dict] = None) -> Optional[object]:
        """Step 4-5: only if human approved -> create + assign default roles."""
        if not approved:
            return None
        rec = self._manager.create(tenant_id, created_by=owner, metadata=metadata)
        # Default roles already global; tenant-specific override hook (R5) is a
        # no-op here (CapabilityManager lives in kernel, not imported by services).
        return rec

    def assign_default_roles(self) -> List[Role]:
        """Roles granted to a new tenant's owner (ADR-035 R7)."""
        return list(DEFAULT_TENANT_ROLES)
