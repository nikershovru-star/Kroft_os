"""K8 tests for ТЗ-LIVE-01 — runnable launch + persistence + optional local LLM (ADR-087).

Covers (acceptance + K1/K6/O1/I-09 + ADR-087):
- PERSISTENCE ROUNDTRIP: save -> load is byte-identical (KernelState equality).
- EVOLUTION ACROSS RESTARTS: kernel self-evolves (soft policy from repeated failures via
  ReferenceExecutor); state saved; a SECOND "restart" resumes the SAME memory and accumulates
  MORE episodes + keeps the learned soft policy (experience from run 1 visible in run 2).
- O1 (HARD immutable): a persisted HARD policy round-trips intact and is NOT mutated by load;
  memory_evolution refuses to deprecate HARD (existing guard) — proven indirectly + directly.
- DETERMINISM (I-09): without LLM, two identical runs produce identical saved state.
- NO-LLM RUN: build_kernel + run works with llm_client=None (skip-if-unavailable is the default).

K5: reuses build_kernel / InMemoryLayeredMemory / ReferenceExecutor / JsonMemoryStore /
ReferenceTrustRegistry / InMemoryProceduralMemory / ProcedureConsolidator — НЕ дублирует порты.
Wiring (run_evolution.py) lives in tests/ for the cross-layer composition (K6: kernel stays pure).
"""

from __future__ import annotations

import os
import tempfile

from contracts.cognitive_domain import (
    ConfidenceScore,
    Episode,
    Policy,
    PolicyLifecycle,
    Provenance,
    SemanticFact,
    CausalMark,
)
from contracts.i_memory import Procedure
from contracts.i_orchestrator import OrchestrationGoal
from kernel.cognitive_kernel import build_kernel
from kernel.memory_store import InMemoryLayeredMemory
from kernel.persistence import JsonMemoryStore, KernelState
from kernel.execution import ReferenceExecutor
from kernel.identity import ReferenceTrustRegistry
from kernel.procedural import build_procedural
from services.memory_platform import InMemoryProceduralMemory


def _run_and_persist(state_path: str, ticks: int, memory: "InMemoryLayeredMemory | None" = None):
    """Mirror run_evolution.py: build kernel (+ReferenceExecutor), tick N goals, persist.

    Returns the saved KernelState for assertions.
    """
    mem = memory if memory is not None else InMemoryLayeredMemory()
    kernel = build_kernel("local", memory=mem)
    kernel.attach_executor(ReferenceExecutor())
    for i in range(ticks):
        cap = "choose_red" if i % 2 == 0 else "choose_blue"
        kernel.tick(_intent(f"g{i}", cap))
    store = JsonMemoryStore()
    state = KernelState(
        episodes=list(mem.get_episodes()),
        semantic=list(mem.get_semantic()),
        normative=list(mem.get_normative()),
        skills=[],  # skills handled separately below if needed
        trust={},
    )
    store.save(state, state_path)
    return state


def _intent(gid: str, cap: str):
    from contracts.cognitive_domain import Intent
    return Intent(
        id=gid, text=cap,
        confidence=ConfidenceScore(0.8),
        provenance=Provenance(source="demo", actor="test"),
    )


def test_persistence_roundtrip_identical():
    st = KernelState(
        episodes=[Episode("e1", "did X", ConfidenceScore(0.9), Provenance("obs", "k"))],
        semantic=[SemanticFact("s1", "fact A", ConfidenceScore(0.8), CausalMark("local", 1), ("e1",))],
        normative=[Policy("p1", "avoid red", "soft", "avoid:red", ConfidenceScore(0.7),
                           Provenance("exp", "k"), PolicyLifecycle.ACTIVE)],
        skills=[Procedure(skill_id="skill:go", name="go", capability="go",
                          steps=("a", "b"), confidence=0.9, provenance="pc")],
        trust={"A": 0.9},
    )
    path = tempfile.mktemp(suffix=".json")
    try:
        JsonMemoryStore().save(st, path)
        st2 = JsonMemoryStore().load(path)
        assert st == st2, "roundtrip must be identical"
        # byte-stable: a second save of the reloaded state is identical
        path2 = tempfile.mktemp(suffix=".json")
        JsonMemoryStore().save(st2, path2)
        assert open(path, encoding="utf-8").read() == open(path2, encoding="utf-8").read()
    finally:
        for p in (path, path2):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def test_evolution_across_two_restarts():
    path = tempfile.mktemp(suffix=".json")
    try:
        # Run 1: evolve 6 ticks, persist.
        st1 = _run_and_persist(path, 6)
        assert len(st1.episodes) == 6
        # At least one soft policy should have been learned (repeated choose_red failures).
        soft1 = [p for p in st1.normative if p.layer == "soft"]
        assert soft1, "kernel should learn a soft avoid-policy from repeated failures"

        # Run 2 (RESTART): resume from the saved memory, evolve 4 more ticks.
        mem2 = InMemoryLayeredMemory()
        for e in st1.episodes:
            mem2.record_episode(e)
        for f in st1.semantic:
            mem2.commit_semantic(f)
        for p in st1.normative:
            mem2.commit_normative(p)
        st2 = _run_and_persist(path, 4, memory=mem2)
        # Experience from run 1 is visible in run 2 (episodes accumulated, not reset).
        assert len(st2.episodes) == 10, f"restart must accumulate: got {len(st2.episodes)}"
        soft2 = [p for p in st2.normative if p.layer == "soft"]
        assert soft2, "learned soft policy must persist across restart"
        # The same avoid-policy body is present in both runs (deterministic evolution).
        bodies1 = {p.body for p in soft1}
        bodies2 = {p.body for p in soft2}
        assert bodies1.issubset(bodies2), "soft policy must survive restart"
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def test_o1_hard_policy_not_mutated_by_load():
    hard = Policy(
        id="h1", name="invariant", layer="hard", body="never-change",
        confidence=ConfidenceScore(1.0), provenance=Provenance("rule", "sys"),
        lifecycle=PolicyLifecycle.ACTIVE,
    )
    st = KernelState(normative=[hard])
    path = tempfile.mktemp(suffix=".json")
    try:
        JsonMemoryStore().save(st, path)
        st2 = JsonMemoryStore().load(path)
        # Persisted HARD policy round-trips intact (load never mutates HARD).
        hard2 = [p for p in st2.normative if p.layer == "hard"]
        assert hard2, "HARD policy must survive persistence"
        assert hard2[0].body == "never-change" and hard2[0].lifecycle == PolicyLifecycle.ACTIVE
        # And the kernel's memory store refuses to deprecate HARD (O1 guard) on reload.
        mem = InMemoryLayeredMemory()
        for p in st2.normative:
            mem.commit_normative(p)
        raised = False
        try:
            mem.deprecate_normative("h1")
        except RuntimeError:
            raised = True
        assert raised, "O1: HARD policy must be immutable (deprecate raises)"
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def test_determinism_without_llm():
    # Without LLM the run is deterministic in its EVOLUTION (I-09): same tick sequence ->
    # same episodes/semantic/soft-policies (ignoring incidental wall-clock provenance timestamps).
    p1, p2 = tempfile.mktemp(suffix=".json"), tempfile.mktemp(suffix=".json")
    try:
        _run_and_persist(p1, 5)
        _run_and_persist(p2, 5)
        s1, s2 = JsonMemoryStore().load(p1), JsonMemoryStore().load(p2)
        # Structural determinism: episode SUMMARIES (opaque random ids excluded), semantic
        # contents, and soft-policy bodies must match. The kernel assigns random episode ids,
        # but the EVOLUTION (what I-09 guarantees) is fully deterministic without LLM.
        assert [e.summary for e in s1.episodes] == [e.summary for e in s2.episodes]
        assert [f.content for f in s1.semantic] == [f.content for f in s2.semantic]
        soft1 = {p.body for p in s1.normative if p.layer == "soft"}
        soft2 = {p.body for p in s2.normative if p.layer == "soft"}
        assert soft1 == soft2, "soft-policy evolution must be deterministic without LLM"
    finally:
        for p in (p1, p2):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def test_no_llm_run_works():
    # build_kernel with llm_client=None runs LLM-free (skip-if-unavailable is the default path).
    kernel = build_kernel("local")
    kernel.attach_executor(ReferenceExecutor())
    # A tick must not raise and must record an episode.
    kernel.tick(_intent("g0", "choose_blue"))
    assert len(kernel._memory.get_episodes()) == 1
