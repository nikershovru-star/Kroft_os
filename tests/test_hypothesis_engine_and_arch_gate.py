"""Tests: kernel/hypothesis_engine.py + kernel/arch_gate.py."""

from __future__ import annotations

import textwrap

from kernel.hypothesis_engine import ReferenceHypothesisEngine
from kernel.arch_gate import run


def test_hypothesis_engine_generates_hypothesis():
    engine = ReferenceHypothesisEngine(threshold_ratio=0.1)
    gap = type("Gap", (), {
        "name": "retrieval",
        "status": "degraded",
        "score": 0.55,
        "target": 0.9,
        "gap": 0.35,
        "metric": "R@5",
        "evidence": "low recall on cross-domain queries",
    })()
    hypothesis = engine.formulate(gap)
    assert hypothesis is not None
    assert hypothesis.metric == "R@5"
    assert hypothesis.acceptance_threshold == round(0.035, 6)
    assert "retrieval capability gap" in hypothesis.problem


def test_hypothesis_engine_skips_non_gap():
    engine = ReferenceHypothesisEngine()
    gap = type("Gap", (), {
        "name": "retrieval",
        "status": "ok",
        "score": 0.95,
        "target": 0.9,
        "gap": 0.0,
        "metric": "R@5",
        "evidence": "",
    })()
    assert engine.formulate(gap) is None


def test_hypothesis_engine_formulate_from_causal():
    engine = ReferenceHypothesisEngine()
    gap = type("Gap", (), {
        "name": "planning",
        "status": "missing",
        "score": 0.0,
        "target": 0.8,
        "gap": 0.8,
        "metric": "plan_success_rate",
        "evidence": "no planner wired",
    })()
    causal = type("Causal", (), {
        "observation": "planner step failed",
        "outcome": "agent loop aborted",
        "change": "planner removed",
        "action": "skip planning",
    })()
    hypothesis = engine.formulate_from_causal(gap, causal)
    assert hypothesis is not None
    assert hypothesis.suspected_cause == "planner removed"


def test_akb_gate_smoke_positive(monkeypatch, tmp_path):
    root = tmp_path
    akb = root / "docs" / "architecture" / "AKB"
    akb.mkdir(parents=True)
    (akb / "import_matrix.yaml").write_text(
        textwrap.dedent(
            """
            version: 1
            matrix:
              contracts: []
              kernel: [contracts, runtime]
              services: [contracts]
              adapters: [contracts]
              composition: [contracts, kernel, services, adapters]
              cli: [composition, contracts]
            scanned_packages:
              - contracts
              - kernel
              - services
              - adapters
              - composition
              - cli
            stdlib_bases:
              - os
              - sys
              - typing
              - abc
              - dataclasses
              - pathlib
              - json
              - time
              - uuid
              - re
            """
        ),
        encoding="utf-8",
    )
    kernel_pkg = root / "kernel"
    kernel_pkg.mkdir()
    (kernel_pkg / "clean.py").write_text(
        "from contracts.i_llm import ILlm\nfrom runtime.clock import Clock\n",
        encoding="utf-8",
    )
    services_pkg = root / "services"
    services_pkg.mkdir()
    (services_pkg / "clean.py").write_text(
        "from contracts.i_knowledge import IKnowledgeGraph\n",
        encoding="utf-8",
    )
    import kernel.arch_gate as ag
    ag.ROOT = root
    code, _ = ag.run()
    assert code == 0


def test_akb_gate_detects_kernel_violation(monkeypatch, tmp_path):
    root = tmp_path
    akb = root / "docs" / "architecture" / "AKB"
    akb.mkdir(parents=True)
    (akb / "import_matrix.yaml").write_text(
        textwrap.dedent(
            """
            version: 1
            matrix:
              contracts: []
              kernel: [contracts, runtime]
              services: [contracts]
            scanned_packages:
              - contracts
              - kernel
              - services
            stdlib_bases:
              - os
              - sys
              - typing
              - abc
              - dataclasses
              - pathlib
              - json
              - time
              - uuid
              - re
            """
        ),
        encoding="utf-8",
    )
    kernel_pkg = root / "kernel"
    kernel_pkg.mkdir()
    (kernel_pkg / "bad.py").write_text(
        "from services.approval_gate import ApprovalGate\n",
        encoding="utf-8",
    )
    import kernel.arch_gate as ag
    ag.ROOT = root
    code, violations = ag.run()
    assert code == 1
    assert any("imports 'services'" in v.message for v in violations)
