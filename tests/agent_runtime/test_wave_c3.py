"""(tests/agent_runtime) Phase C Wave C3 — delegation trust-delta + telemetry (ADR-103).

K8. Проверяет (без новых портов, K5 — переиспользует ITrustRegistry + ITelemetrySink):
  - delegated success -> trust исполнителя растёт (record_outcome SOFT);
  - delegated failure -> trust понижается;
  - telemetry-событие "agent_runtime.delegation" записано (value 1.0 success / 0.0 fail);
  - без trust_registry/telemetry поведение НЕИЗМЕННО (backward-compat);
  - determinism (I-09): тот же goal -> тот же root_goal_id.
"""
from contracts.i_agent_executor import IAgentExecutor
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from kernel.identity import ReferenceTrustRegistry
from adapters.in_memory_telemetry import InMemoryTelemetrySink as InMemoryTelemetry
from services.agent_runtime import AgentRuntime
from services.blackboard import InMemoryBlackboard
from services.delegation_service import DelegationService


class _StubExecutor(IAgentExecutor):
    """Минимальный IAgentExecutor для изолированного теста trust-delta."""
    def __init__(self, capability: str, success: bool) -> None:
        self._cap = capability
        self._success = success

    def can_execute(self, goal: OrchestrationGoal) -> bool:
        return goal.capability == self._cap

    def execute(self, goal: OrchestrationGoal) -> TaskOutcome:
        return TaskOutcome(success=self._success, detail="stub")


def _rt(trust=None, telemetry=None, success=True):
    ex = _StubExecutor("research", success=success)
    return AgentRuntime(
        executor=ex,
        blackboard=InMemoryBlackboard(),
        delegation=DelegationService(max_depth=8),
        root_capability="research",
        trust_registry=trust,
        telemetry=telemetry,
    )


def test_success_raises_trust():
    trust = ReferenceTrustRegistry()
    rt = _rt(trust=trust, success=True)
    before = trust.current_trust("research")  # default 0.5 (no outcome yet)
    assert before == 0.5
    rt.delegate_step("root", OrchestrationGoal(goal_id="c1", capability="research", payload="x"))
    after = trust.current_trust("research")
    assert after > before, f"trust должен расти: {before} -> {after}"


def test_failure_lowers_trust():
    trust = ReferenceTrustRegistry()
    rt = _rt(trust=trust, success=False)
    # сначала поднимем trust success-ом, затем упадём
    rt2 = _rt(trust=trust, success=True)
    rt2.delegate_step("root", OrchestrationGoal(goal_id="ok", capability="research", payload="x"))
    high = trust.current_trust("research")
    rt.delegate_step("root", OrchestrationGoal(goal_id="bad", capability="research", payload="x"))
    low = trust.current_trust("research")
    assert low < high, f"failure должен понижать trust: {high} -> {low}"


def test_telemetry_records_delegation_events():
    tel = InMemoryTelemetry()
    rt = _rt(telemetry=tel, success=True)
    rt.delegate_step("root", OrchestrationGoal(goal_id="c1", capability="research", payload="x"))
    pts = tel.query("agent_runtime.delegation", window_sec=10_000)
    assert len(pts) == 1
    assert pts[0].value == 1.0
    # failure event
    rt2 = _rt(telemetry=tel, success=False)
    rt2.delegate_step("root", OrchestrationGoal(goal_id="c2", capability="research", payload="x"))
    pts2 = tel.query("agent_runtime.delegation", window_sec=10_000)
    assert len(pts2) == 2
    assert any(p.value == 0.0 for p in pts2)


def test_backward_compat_without_deps():
    """Без trust/telemetry поведение НЕИЗМЕННО (delegate_step работает, не падает)."""
    rt = _rt(trust=None, telemetry=None, success=True)
    out = rt.delegate_step("root", OrchestrationGoal(goal_id="c1", capability="research", payload="x"))
    assert out.success
    # blackboard запись есть (stigmergy), но trust/telemetry не инжектнуты
    assert rt._trust is None and rt._telemetry is None


def test_determinism_root_goal_id():
    rt = _rt()
    r1 = rt.run_workflow("same goal")
    r2 = rt.run_workflow("same goal")
    assert r1.root_goal_id == r2.root_goal_id
