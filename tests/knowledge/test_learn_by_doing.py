"""Vertical slice: KROFT_OS learns by doing (file + command) and reuses experience.

Proof, not architecture: a real Action is executed by the REAL backend
(RealWorldExecutor -> LocalFileSystemAdapter / TerminalExecutor), the outcome is
fed into the EXISTING learning pipeline (_evolve_procedural_from_runtime ->
SkillEvolver + InMemoryProceduralMemory), persisted to KnowledgeSnapshotStore,
and recovered by a fresh KroftApp -> demonstrated reuse across restart.

Reuses (no new layer/port/DTO): RealWorldExecutor, CognitiveKernel._outcomes,
LiveMetricsCollector, SkillEvolver, InMemoryProceduralMemory, KnowledgeSnapshotStore.
K5/K6: composition-only wiring; kernel/contracts untouched beyond P.1-P.3.
"""

from __future__ import annotations
import pytest

import json
import os
import tempfile

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig
from contracts.cognitive_domain import (
    Action, ConfidenceScore, ExecutionOutcome, Plan, Provenance, ProvenanceType,
)


def _exec_and_learn(app, action, capability_key):
    """Execute a REAL action, feed the outcome into the existing learning pipeline."""
    # mirror what CognitiveKernel Execute-phase does: the selected plan carries the
    # structured execution intent, so capability is keyed by the REAL action kind.
    app.kernel._last_selected_plan = Plan(
        id=f"plan-{capability_key}", goal_id="g", steps=(f"{capability_key} op",),
        confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
        provenance=Provenance(source="decision", actor="kernel"),
        execution_steps=({"kind": capability_key},),
    )
    result = app.kernel._executor.execute(action)
    # mirror what CognitiveKernel Execute-phase does (ТЗ-EX-01 / PHASE O.7)
    outcome = ExecutionOutcome(
        episode_id=f"ep-{capability_key}",
        success=result.success,
        utility=result.reward,
        confidence=result.confidence,
        causal=result.causal,
    )
    app.kernel._outcomes.append(outcome)
    if result.success:
        app.kernel._metrics.record_success("execution_success_rate")
    else:
        app.kernel._metrics.record_failure("execution_success_rate")
    # feed REAL outcomes into SkillEvolver (ТЗ-PHASE-L/M)
    app._evolve_procedural_from_runtime()
    return result


@pytest.mark.slow
def test_learn_by_doing_file_and_command_and_reload():
    tmp = tempfile.mkdtemp()
    snap = os.path.join(tmp, "knowledge.json")

    # ---- Slice 1: FILE ----
    app = KroftApp(KroftConfig(node_id="learn1", llm="none", ticks=0,
                               knowledge_snapshot=snap,
                               vault="C:/Users/Nikita/Documents/Obsidian Vault/02-Projects/KROFT_OS"))
    assert type(app.kernel._executor).__name__ == "RealWorldExecutor"

    fpath = os.path.join(tmp, "hello.txt")
    # real file write through the filesystem backend
    r1 = _exec_and_learn(
        app,
        Action(id="f1", kind="file", payload=f"write:{fpath}|hello world",
               confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
               provenance=Provenance(source="decision", actor="kernel")),
        "file",
    )
    assert r1.success is True, r1.observation
    assert os.path.exists(fpath)
    assert open(fpath, encoding="utf-8").read() == "hello world"

    # repeat a similar file action -> runs accumulate under exec:file
    r2 = _exec_and_learn(
        app,
        Action(id="f2", kind="file", payload=f"write:{fpath}|hello again",
               confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
               provenance=Provenance(source="decision", actor="kernel")),
        "file",
    )
    assert r2.success is True
    rec_file = app.procedural._procedures.get("exec:file")
    assert rec_file is not None, "learning must key file experience by exec:file"
    assert rec_file["runs"] >= 2, rec_file
    assert rec_file["successes"] >= 2, rec_file

    # ---- Slice 2: COMMAND ----
    r3 = _exec_and_learn(
        app,
        Action(id="c1", kind="command", payload="echo learned",
               confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
               provenance=Provenance(source="decision", actor="kernel")),
        "command",
    )
    assert r3.success is True, r3.observation
    rec_cmd = app.procedural._procedures.get("exec:command")
    assert rec_cmd is not None and rec_cmd["runs"] >= 1, rec_cmd

    # file and command are keyed separately (reuse is typed, not collapsed to "demo")
    assert "exec:file" in app.procedural._procedures
    assert "exec:command" in app.procedural._procedures

    # ---- Persist + reload (proves memory survives restart) ----
    app._save_knowledge()
    assert os.path.exists(snap)

    app2 = KroftApp(KroftConfig(node_id="learn2", llm="none", ticks=0,
                                knowledge_snapshot=snap,
                                vault="C:/Users/Nikita/Documents/Obsidian Vault/02-Projects/KROFT_OS"))
    # the accumulated file experience was restored -> reuse after restart
    restored = app2.procedural._procedures.get("exec:file")
    assert restored is not None, "exec:file experience must survive restart"
    assert restored["runs"] >= 2, restored
    assert restored["successes"] >= 2, restored
    # and a fresh similar file action now builds on the restored record
    r4 = _exec_and_learn(
        app2,
        Action(id="f3", kind="file", payload=f"write:{fpath}|reuse works",
               confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
               provenance=Provenance(source="decision", actor="kernel")),
        "file",
    )
    assert r4.success is True
    assert app2.procedural._procedures["exec:file"]["runs"] >= 3, \
        "restored experience must accumulate further"
