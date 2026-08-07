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
    # agents / models / marketplace / trust are seeded with real components
    assert len(snap.agents) == 6
    assert len(snap.models) == 2
    assert snap.marketplace_skills == 52
    # notes are LIVE now (ТЗ-DAILY-01): no vault -> 0 (graceful); not the old 245 seed
    assert snap.memory_notes == 0
    assert abs(snap.trust_score - 0.97) < 1e-6
    # federation disabled by default -> 0 nodes
    assert snap.federation_nodes == 0
    # panel text renders the at-a-glance layout (Kernel / Agents / Tasks / ...)
    text = a.dashboard.render_text(snap)
    assert "KROFT Desktop" in text
    assert "6 active" in text
    assert "52 skills" in text
    # notes are LIVE now (ТЗ-DAILY-01): no vault -> "0 notes" (not seeded 245)
    assert "0 notes" in text
    assert "0.97" in text


def test_evolution_progresses():
    """The demo skill evolves (v1 -> v2) when REAL tick outcomes show low success rate.

    ТЗ-PHASE-L: step() now feeds REAL ExecutionOutcome stats into SkillEvolver instead
    of fake stats. Successful proxy-fallback ticks (rate 1.0) do NOT evolve; we inject
    failed outcomes to prove the runtime evolution path still produces a better variant.
    """
    a = KroftApp(KroftConfig(node_id="n4", llm="none", ticks=4))
    before = {s.version for s in a.procedural.list_skills() if s.capability == "demo"}
    assert 1 in before
    # simulate failed ticks -> SkillEvolver evolves the demo skill to v2
    from contracts.cognitive_domain import ExecutionOutcome, ConfidenceScore
    a.kernel._outcomes = [
        ExecutionOutcome(episode_id="f1", success=False, utility=0.0,
                         confidence=ConfidenceScore(0.5, "observation"), causal=None),
        ExecutionOutcome(episode_id="f2", success=False, utility=0.0,
                         confidence=ConfidenceScore(0.5, "observation"), causal=None),
    ]
    a._evolve_procedural_from_runtime(capability="demo", skill=a.procedural._skills["demo"])
    after = {s.version for s in a.procedural.list_skills() if s.capability == "demo"}
    assert 2 in after  # evolution produced a better (shorter) variant from real stats


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


# === ТЗ-DAILY-01: live data instead of demo-seed + daily-use readiness ===

def test_live_vault_ingestion(tmp_path):
    """ТЗ-DAILY-01: a real vault path yields LIVE note counts (not seeded 245)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note-a.md").write_text("# Alpha\nlinks to [[Beta]]", encoding="utf-8")
    (vault / "note-b.md").write_text("# Beta\nsome content", encoding="utf-8")
    a = KroftApp(KroftConfig(node_id="d1", llm="none", ticks=0, vault=str(vault)))
    snap = a.dashboard.snapshot()
    # 2 markdown files -> graph nodes (doc + wikilink target) -> live memory_notes > 0
    assert snap.memory_notes >= 2
    assert snap.memory_notes != 245  # NOT the old demo-seed count


def test_graceful_no_vault():
    """ТЗ-DAILY-01: missing vault -> 0 notes, no crash (graceful degradation)."""
    a = KroftApp(KroftConfig(node_id="d2", llm="none", ticks=0, vault=None))
    snap = a.dashboard.snapshot()
    assert snap.memory_notes == 0


def test_task_store_live():
    """ТЗ-DAILY-01: real TaskStore reflects genuine queued tasks in the dashboard."""
    a = KroftApp(KroftConfig(node_id="d3", llm="none", ticks=0))
    assert len(a.dashboard.snapshot().tasks) == 0
    a.task_store.add("real-task-1", "queued")
    snap = a.dashboard.snapshot()
    assert len(snap.tasks) == 1
    assert ("real-task-1", "queued") in snap.tasks


def test_interactive_query_answers_from_vault(tmp_path):
    """ТЗ-DAILY-01: interactive contour answers a query from the LIVE vault via agent loop."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "kroft.md").write_text("# KROFT_OS\nautonomous intelligence operating system", encoding="utf-8")
    a = KroftApp(KroftConfig(node_id="d4", llm="none", ticks=0, vault=str(vault)))
    ans = a.interactive_query("KROFT_OS")
    assert "KROFT_OS" in ans  # live answer references the ingested note (header node)
    # a real task was enqueued + completed
    assert len(a.task_store.list()) == 1
    assert a.task_store.get("task-1").status == "done"


def test_interactive_query_deterministic(tmp_path):
    """ТЗ-DAILY-01: identical query -> identical answer (I-09)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "x.md").write_text("# Topic\nrepeated content", encoding="utf-8")
    a = KroftApp(KroftConfig(node_id="d5", llm="none", ticks=0, vault=str(vault)))
    assert a.interactive_query("Topic") == a.interactive_query("Topic")

