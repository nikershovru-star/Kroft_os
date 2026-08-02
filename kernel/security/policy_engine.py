"""Authorization Policy Engine — orchestrator (TZ-SEC-001 WP-03, ADR-033).

K1-compliant: contracts + stdlib only. Wires CapabilityManager + ApprovalManager:
  Agent -> Role -> CapabilityManager.authorize -> (allow | deny | needs_approval).
This is the kernel-side authorization gate. It does NOT execute tools; callers
invoke it before tool.exec. The existing services/policy_engine.py (model
selection) is unrelated and untouched.
"""
from __future__ import annotations

from typing import List

from contracts.security import (
    AuthDecision,
    Capability,
    IApprovalManager,
    ICapabilityManager,
    IPolicyEngine,
    Role,
)
from contracts.tenant import ITenantIsolator


class AuthorizationEngine(IPolicyEngine):
    def __init__(self, manager: ICapabilityManager,
                 approval: IApprovalManager | None = None,
                 isolator: ITenantIsolator | None = None) -> None:
        self._manager = manager
        self._approval = approval
        self._isolator = isolator

    def authorize(self, agent_id: str, role: Role, required: Capability) -> AuthDecision:
        ctx = self._manager.context_for(agent_id, role)
        decision = self._manager.authorize(ctx, required)
        if decision.requires_approval and self._approval is not None:
            # Raise an approval request; caller must wait/decide.
            req = self._approval.request(agent_id, required.id, "")
            decision._approval_id = req._id  # type: ignore[attr-defined]
        return decision

    def authorize_tool(self, agent_id: str, role: Role, tool_name: str,
                       required: List[str]) -> AuthDecision:
        # A tool may require several capabilities; ALL must be allowed.
        last: AuthDecision | None = None
        for spec in required:
            cap = Capability.parse(spec)
            d = self.authorize(agent_id, role, cap)
            last = d
            if not d.allowed:
                return d
        if last is None:
            # No capabilities declared -> default deny (fail-closed).
            return AuthDecision.deny(
                Capability.parse("Tool.*"),
                f"tool {tool_name} declares no capabilities",
            )
        return last

    def authorize_cross_tenant(self, src_tenant: str, dst_tenant: str) -> AuthDecision:
        """Cross-tenant access is ALWAYS denied (TZ-MULTI-001 R6, ADR-035 K6).

        Agents in tenant=A may never read/write/call resources in tenant=B. The
        boundary is enforced explicitly via ITenantIsolator.check_boundary; if an
        isolator is wired it is consulted, but the default outcome is deny.
        """
        if self._isolator is not None and self._isolator.check_boundary(src_tenant, dst_tenant):
            # Only same-tenant or explicitly global tenants pass (isolator policy).
            return AuthDecision.allow(Capability.parse("Admin.Tenant"))
        return AuthDecision.deny(
            Capability.parse("Admin.Tenant"),
            f"cross-tenant access {src_tenant} -> {dst_tenant} denied (R6)",
        )
