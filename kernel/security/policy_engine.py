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


class AuthorizationEngine(IPolicyEngine):
    def __init__(self, manager: ICapabilityManager,
                 approval: IApprovalManager | None = None) -> None:
        self._manager = manager
        self._approval = approval

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
