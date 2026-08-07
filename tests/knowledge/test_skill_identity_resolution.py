"""ТЗ-PHASE-M: Skill Identity Resolution + RuntimeSupervisor wiring.

Targeted proof (K5 + I-09):
  Task 1: _resolve_skill_from_plan() maps the last executed Plan (by steps) to the
          matching Procedure in ProceduralMemory, so runtime evolution targets the real
          executed skill (not a hardcoded demo). Composition-only (no kernel change).
  Task 2: passing a LiveMetricsCollector via build_cognitive_kernel wires the kernel's
          existing RuntimeSupervisor hook (collect->reflect->apply, SOFT-only, O1) — no
          kernel change, reuses RuntimeSupervisor + ILiveMetricsCollector.
"""

from __future__ import annotations

from composition.run_kroft import KroftApp, KroftConfig
from contracts.i_memory import Procedure
from contracts.cognitive_domain import PolicyLifecycle


def test_skill_identity_resolves_executed_plan(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "m.json")

    a = KroftApp(KroftConfig(node_id="m1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    real_proc = Procedure(
        skill_id="proc-resolve", name="resolver-test", capability="resolver",
        steps=("observe world", "decide plan", "execute"), confidence=0.5,
    )
    a.procedural.store_skill(real_proc)

    class _FakePlan:
        steps = ("observe world", "decide plan", "execute")

    a.kernel._last_selected_plan = _FakePlan()
    cap, resolved = a._resolve_skill_from_plan()
    assert cap == "resolver"
    assert resolved is real_proc


def test_runtime_supervisor_wired_via_live_metrics(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "m2.json")

    a = KroftApp(KroftConfig(node_id="m2", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    # Task 2: kernel's RuntimeSupervisor hook is now active (no kernel change)
    assert a.kernel._supervisor is not None
    # several ticks must not raise (supervisor.step runs every N ticks, SOFT-only)
    for _ in range(4):
        a.step()
    assert True  # reached here => supervisor wired + loop stable
