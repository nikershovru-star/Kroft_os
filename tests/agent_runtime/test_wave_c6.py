"""(tests/agent_runtime) Phase C Wave C6 — Approval Gate (ADR-103).

K8. Без новых портов (K5 — переиспользует IActionLog для audit). Проверяет:
  - sensitive действие без одобрения (approver=False) -> denied (default-deny);
  - approve (approver=True) -> проходит;
  - timeout (slow approver > ttl) -> denied (НЕ livelock);
  - audit записан в IActionLog;
  - без gate (approval_gate=None) поведение НЕИЗМЕННО (backward-compat).
"""
import time

from contracts.i_approval_gate import ApprovalRequest, IApprovalGate
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.i_identity import IActionLog
from kernel.identity import ReferenceActionLog, ReferenceTrustRegistry
from services.agent_runtime import AgentRuntime
from services.blackboard import InMemoryBlackboard
from services.delegation_service import DelegationService
from services.approval_gate import ApprovalGate


class _StubExecutor:
    """Минимальный executor (НЕ IAgentExecutor, просто duck-type для теста через subclass)."""
    def can_execute(self, goal):
        return goal.capability in ("research", "finance", "coding")
    def execute(self, goal):
        return TaskOutcome(success=True, detail=f"ran {goal.capability}")


def _rt(approval_gate=None, sensitive=()):
    return AgentRuntime(
        executor=_StubExecutor(),
        blackboard=InMemoryBlackboard(),
        delegation=DelegationService(max_depth=8),
        root_capability="research",
        approval_gate=approval_gate,
        sensitive_capabilities=sensitive,
    )


def _approver_flag(flag: bool):
    return lambda req: flag


def _slow_approver(_req):
    time.sleep(2.0)
    return True


def test_sensitive_denied_without_approval():
    gate = ApprovalGate(approver=_approver_flag(False), action_log=ReferenceActionLog(),
                        sensitive_capabilities={"finance"}, ttl_sec=2.0)
    rt = _rt(approval_gate=gate, sensitive=("finance",))
    out = rt.delegate_step("root", OrchestrationGoal(goal_id="f1", capability="finance", payload="x"))
    assert not out.success
    assert "approval denied" in out.detail.lower()


def test_sensitive_approved_passes():
    gate = ApprovalGate(approver=_approver_flag(True), action_log=ReferenceActionLog(),
                        sensitive_capabilities={"finance"}, ttl_sec=2.0)
    rt = _rt(approval_gate=gate, sensitive=("finance",))
    out = rt.delegate_step("root", OrchestrationGoal(goal_id="f1", capability="finance", payload="x"))
    assert out.success
    assert "ran finance" in out.detail


def test_timeout_default_deny_no_livelock():
    gate = ApprovalGate(approver=_slow_approver, action_log=ReferenceActionLog(),
                        sensitive_capabilities={"finance"}, ttl_sec=0.3)
    rt = _rt(approval_gate=gate, sensitive=("finance",))
    t0 = time.time()
    out = rt.delegate_step("root", OrchestrationGoal(goal_id="f1", capability="finance", payload="x"))
    dt = time.time() - t0
    assert not out.success
    assert "timed out" in out.detail.lower()
    assert dt < 2.0  # не ждали slow approver (2s), таймаут сработал быстрее


def test_audit_logged():
    log = ReferenceActionLog()
    gate = ApprovalGate(approver=_approver_flag(False), action_log=log,
                        sensitive_capabilities={"finance"}, ttl_sec=2.0)
    rt = _rt(approval_gate=gate, sensitive=("finance",))
    rt.delegate_step("root", OrchestrationGoal(goal_id="f1", capability="finance", payload="x"))
    entries = log.list("finance")  # agent_id = executor_id = capability (Флаг 2 C1)
    assert any("DENIED" in e for e in entries), entries


def test_backward_compat_without_gate():
    """Без gate поведение НЕИЗМЕННО: sensitive cap исполняется без блокировки."""
    rt = _rt(approval_gate=None, sensitive=())
    out = rt.delegate_step("root", OrchestrationGoal(goal_id="f1", capability="finance", payload="x"))
    assert out.success  # gateway отсутствует -> исполнение как раньше
    assert rt._approval is None
