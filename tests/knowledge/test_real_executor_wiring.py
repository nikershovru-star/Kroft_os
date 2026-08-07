"""ТЗ-PHASE-N: Real Execution Backend wiring (IExecutor) closes the outcome-proxy.

Targeted proof (K5 + I-09): run_kroft wires ReferenceExecutor via the existing
kernel.attach_executor API, so CognitiveKernel.tick records REAL success/failure
outcomes (not the always-success proxy). With a plan that does NOT contain
'choose_blue', the executor returns failure -> at least one ExecutionOutcome has
success=False, and the real failure feeds SkillEvolver (demo skill evolves v1->v2
with NO fake stats). After a cold boot WITHOUT the vault the evolved skill restores.
No kernel change, no new port/layer/DTO (K5/K6); reuses IExecutor/ReferenceExecutor.
"""

from __future__ import annotations

import os

from composition.run_kroft import KroftApp, KroftConfig


def test_real_executor_wired_and_emits_failure(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("# Note\ncontent", encoding="utf-8")
    snap = str(tmp_path / "n.json")

    a = KroftApp(KroftConfig(node_id="n1", llm="none", ticks=0,
                             vault=str(vault), knowledge_snapshot=snap))
    # executor is wired -> real outcomes (not proxy)
    assert a.kernel._executor is not None
    before_v = a.procedural._skills["demo"].version

    # 3 real ticks; demo plan lacks 'choose_blue' -> executor returns failure
    for _ in range(3):
        a.step()
    outcomes = list(a.kernel._outcomes)
    assert any(not getattr(o, "success", True) for o in outcomes)

    # real failure feeds SkillEvolver (no fake stats injected)
    after_v = a.procedural._skills["demo"].version
    assert after_v > before_v
    a._save_knowledge()

    # cold boot without vault -> evolved skill restored
    b = KroftApp(KroftConfig(node_id="n2", llm="none", ticks=0,
                             vault=None, knowledge_snapshot=snap))
    assert b.procedural._skills["demo"].version == after_v
    assert len(b.graph.nodes()) >= 1
    assert abs(b.trust.current_trust("agent.research") - 0.97) < 1e-9
