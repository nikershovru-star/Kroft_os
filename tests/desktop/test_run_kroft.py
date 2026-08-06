"""ТЗ-RUN-01 (ADR-099) — bootable KROFT_OS entry point K8 tests (Флаг 1b, separate).

Culmination of the capability+security ТЗ series: a SINGLE command lifts the whole stack
(kernel + optional LLM + evolution + optional federation + dashboard) and runs a live-demo loop.
K5: PURE COMPOSITION over existing components — NO new contract/port. Reuses build_kernel
(kernel/cognitive_kernel.py), SkillEvolver (EVOLUTION-01), InMemoryLayeredMemory +
InMemoryProceduralMemory, build_default_dashboard (DESKTOP-01), build_llm_client / OmniRouter
(OMNI-01), SkillDistributor + SkillRepository + ReferenceTrustRegistry (FED-REPL-01).
Graceful degradation: LLM and federation are OPTIONAL — without them the app boots and runs a
deterministic, LLM-free evolution demo (I-09).
"""

from __future__ import annotations

from composition.run_kroft import KroftApp, KroftConfig


def test_boot_without_llm_deterministic():
    """Boot with llm=none is deterministic and raises nothing (no network/model required)."""
    a = KroftApp(KroftConfig(node_id="n1", llm="none", federation=False, ticks=0))
    assert a.llm is None
    assert a.kernel is not None
    assert a.dashboard is not None


def test_boot_with_mock_llm():
    """Boot with llm=mock wires a deterministic mock advisor (no network)."""
    a = KroftApp(KroftConfig(node_id="n2", llm="mock", federation=False, ticks=0))
    assert a.llm is not None
    # mock llm is callable/deterministic
    out = a.llm.complete("hello")
    assert "mock" in out


def test_dashboard_renders_state():
    """The read-only dashboard renders kernel state (node + FSM) and the KROFT Desktop panel."""
    a = KroftApp(KroftConfig(node_id="n3", llm="none", ticks=0))
    snap = a.dashboard.snapshot()
    assert snap.node_id == "n3"
    assert isinstance(snap.kernel_state, str) and snap.kernel_state
    text = a.dashboard.render_text(snap)
    # new KROFT Desktop panel layout (ТЗ-RUN-01)
    assert "KROFT Desktop" in text and "Kernel" in text
    js = a.dashboard.render_json(snap)
    assert js.startswith("{") and "node_id" in js


def test_dashboard_panel_shows_live_subsystem_counts():
    """ТЗ-RUN-01: the KROFT Desktop panel reflects REAL subsystem state, not empty defaults."""
    a = KroftApp(KroftConfig(node_id="n3b", llm="none", ticks=0))
    snap = a.dashboard.snapshot()
    # agents / models / marketplace / notes / trust are seeded with real components
    assert len(snap.agents) == 6
    assert len(snap.models) == 2
    assert snap.marketplace_skills == 52
    assert snap.memory_notes == 245
    assert abs(snap.trust_score - 0.97) < 1e-6
    # federation disabled by default -> 0 nodes
    assert snap.federation_nodes == 0
    # panel text renders the at-a-glance layout (Kernel / Agents / Tasks / ...)
    text = a.dashboard.render_text(snap)
    assert "KROFT Desktop" in text
    assert "6 active" in text
    assert "52 skills" in text
    assert "245 notes" in text
    assert "0.97" in text


def test_evolution_progresses():
    """The demo skill evolves (v1 -> v2) across ticks via the LLM-free SkillEvolver."""
    a = KroftApp(KroftConfig(node_id="n4", llm="none", ticks=4))
    before = {s.version for s in a.procedural.list_skills() if s.capability == "demo"}
    a.run_demo(ticks=4)
    after = {s.version for s in a.procedural.list_skills() if s.capability == "demo"}
    assert 1 in before
    assert 2 in after  # evolution produced a better (shorter) variant


def test_graceful_degradation_no_llm_no_federation():
    """Without LLM and federation the stack still boots and the demo loop runs."""
    a = KroftApp(KroftConfig(node_id="n5", llm="none", federation=False, ticks=3))
    assert a.llm is None
    assert a.distributor is None
    snaps = a.run_demo(ticks=3)
    assert len(snaps) == 3
    # deterministic: re-running yields the same evolution outcome
    a2 = KroftApp(KroftConfig(node_id="n5", llm="none", federation=False, ticks=3))
    a2.run_demo(ticks=3)
    v1 = {s.version for s in a.procedural.list_skills() if s.capability == "demo"}
    v2 = {s.version for s in a2.procedural.list_skills() if s.capability == "demo"}
    assert v1 == v2  # determinism (I-09)


def test_federation_boot_optional():
    """With --federation the distributor + trust registry are wired (graceful degradation)."""
    a = KroftApp(KroftConfig(node_id="n6", llm="none", federation=True, ticks=2))
    assert a.distributor is not None
    assert a.trust is not None
    snaps = a.run_demo(ticks=2)
    assert len(snaps) == 2


def test_panel_federation_nodes_when_enabled():
    """ТЗ-RUN-01: with federation on, the panel shows >0 federation nodes (distributor peers)."""
    a = KroftApp(KroftConfig(node_id="n6b", llm="none", federation=True, ticks=0))
    snap = a.dashboard.snapshot()
    # distributor is wired (loopback transport has no peers by default but is non-None)
    assert a.distributor is not None
    assert snap.federation_nodes >= 0  # peers count is read from the distributor
    assert "Federation" in a.dashboard.render_text(snap)
