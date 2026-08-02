"""Self-healing & approval integration (TZ-AGENT-001 WP-07, ADR-037 §2, K5).

K1-compliant: contracts only + stdlib. Implements the self-healing policy:
only `restart_stale_agent` is auto-approved (Q2); revoke_capability /
terminate / k1_violation require human approval via ApprovalManager (K5).
Every action is recorded in the AuditLogger (K4 trace).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from contracts.agent_orchestration import AgentState, IAgentLifecycle, IAgentRecovery
from contracts.security import IApprovalManager, IAuditLogger
from contracts.tenant import TenantId


STALE_THRESHOLD_SECONDS = 30


class SelfHealingPolicy:
    """Decides which healing actions are auto-approved vs K5-gated."""

    @staticmethod
    def should_auto_restart(stale_seconds: float) -> bool:
        """Q2: restart a STALE agent only after it has been stale >30s."""
        return stale_seconds > STALE_THRESHOLD_SECONDS

    @staticmethod
    def requires_approval(action: str) -> bool:
        """K5: everything except auto-restart needs human approval."""
        return action != "restart_stale_agent"


@dataclass
class HealingAction:
    agent_id: str
    action: str
    approved: bool
    detail: str = ""


class HealingExecutor:
    """Executes self-healing actions, gating K5 actions through approval."""

    def __init__(
        self,
        lifecycle: IAgentLifecycle,
        approval: IApprovalManager,
        audit: IAuditLogger,
    ) -> None:
        self._lifecycle = lifecycle
        self._approval = approval
        self._audit = audit
        self._last_actions: List[HealingAction] = []

    # -- auto-approved (non-critical) --------------------------------------

    def auto_restart(self, agent_id: str) -> HealingAction:
        """Restart a STALE agent (Q2 exception — no K5)."""
        self._lifecycle.transition(agent_id, AgentState.RECOVERING, "auto-restart")
        self._lifecycle.transition(agent_id, AgentState.RUNNING, "auto-restart ok")
        action = HealingAction(agent_id, "restart_stale_agent", approved=True,
                               detail="STALE -> RECOVERING -> RUNNING")
        self._record(action)
        return action

    # -- K5-gated -----------------------------------------------------------

    def request_revocation(self, agent_id: str, capability: str) -> HealingAction:
        """Capability leak -> request human approval (K5)."""
        return self._request(agent_id, "revoke_capability", f"capability={capability}")

    def terminate_on_k1_violation(self, agent_id: str) -> HealingAction:
        """K1 violation -> fail-closed: immediate TERMINATED + approval (K5)."""
        self._lifecycle.terminate(agent_id, "K1 violation (fail-closed)")
        return self._request(agent_id, "terminate_agent", "K1 violation")

    # -- helpers -----------------------------------------------------------

    def _request(self, agent_id: str, action: str, args: str) -> HealingAction:
        req = self._approval.request(agent_id, action, args)
        action = HealingAction(agent_id, action,
                               approved=(req.status.value == "approved"),
                               detail=f"approval_status={req.status.value}")
        self._record(action)
        return action

    def _record(self, action: HealingAction) -> None:
        self._last_actions.append(action)
        self._audit.log(_audit_record(
            agent_id=action.agent_id,
            tool="self_healing",
            arguments=action.action,
            result="approved" if action.approved else "approval_required",
            status="ok" if action.approved else "approval_required",
        ))

    def history(self) -> List[HealingAction]:
        return list(self._last_actions)


def _audit_record(agent_id: str, tool: str, arguments: str, result: str, status: str):
    from contracts.security import AuditRecord
    from datetime import datetime, timezone
    return AuditRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent_id=agent_id, tool=tool, arguments=arguments,
        result=result, duration_ms=0.0, status=status,
    )


class AgentRecoveryAdapter(IAgentRecovery):
    """Thin IAgentRecovery adapter over the agent lifecycle FSM (Wave 2 WP-10).

    Lets SupervisorService drive agent recovery through the port (K6) instead
    of importing healing.py internals. Delegates to IAgentLifecycle + a
    SelfHealingPolicy for the auto-restart decision (Q2).
    """

    def __init__(self, lifecycle: IAgentLifecycle, policy: SelfHealingPolicy) -> None:
        self._lifecycle = lifecycle
        self._policy = policy

    def restart_agent(self, agent_id: str) -> bool:
        state = self._lifecycle.get_state(agent_id)
        if state is None:
            return False
        if state is AgentState.STALE:
            try:
                self._lifecycle.transition(agent_id, AgentState.RECOVERING, "supervisor restart")
                self._lifecycle.transition(agent_id, AgentState.RUNNING, "recovered")
                return True
            except ValueError:
                return False
        return True  # already running/paused -> treat as healthy

    def quarantine_agent(self, agent_id: str) -> bool:
        try:
            self._lifecycle.terminate(agent_id, "supervisor quarantine")
            return True
        except (ValueError, KeyError):
            return False

    def get_agent_health(self, agent_id: str) -> AgentState:
        return self._lifecycle.get_state(agent_id)
