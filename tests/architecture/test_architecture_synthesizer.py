"""P1-C proof-of-fire: ArchitectureSynthesizer (L8, ADR-0XX).

Self-contained — NO Ollama, NO network. Fake L5/L6/L7 engines prove the
synthesizer correctly folds their outputs into a SynthesisProposal with the
right confidence / flags / change_request.

Proves:
  - clean simulation + non-empty roadmap -> confidence > 0.5, simulation_ok True
  - simulation violation -> simulation_ok False, confidence reduced
  - empty debt + empty roadmap -> confidence == 0.5 (base only)
  - change_request folds roadmap titles + high-severity debt details
  - zero-regression: None engines -> TypeError (contract requires instances)
"""
from __future__ import annotations

from typing import List, Optional

import pytest

from contracts.i_architecture_intelligence import (
    DebtReport,
    EvolutionRoadmap,
    RoadmapItem,
    SimulationResult,
    SynthesisProposal,
)
from services.architecture_intelligence import ArchitectureSynthesizer


class _FakeSimulator:
    def __init__(self, ok: bool = True):
        self._ok = ok
    def simulate_imports(self, files):
        v = [] if self._ok else ["x/kernel.py: forbidden import 'services'"]
        return SimulationResult(ok=self._ok, predicted_violations=v,
                               notes="fake")
    def dry_run_command(self, command):
        return SimulationResult(ok=True)


class _FakeDebt:
    def __init__(self, items=None, score=0.0):
        self._r = DebtReport(score=score, items=items or [], generated_at="")
    def audit(self):
        return self._r


class _FakeEvolution:
    def __init__(self, items=None):
        self._r = EvolutionRoadmap(items=items or [], generated_at="")
    def plan(self):
        return self._r


def test_clean_sim_plus_roadmap_boosts_confidence():
    sim = _FakeSimulator(ok=True)
    debt = _FakeDebt(score=0.2)
    evo = _FakeEvolution([RoadmapItem(title="Harden boundaries",
                                      rationale="drift 0.7",
                                      priority="high",
                                      proposed_adr="ADR-TBD-boundary")])
    prop = ArchitectureSynthesizer().synthesize(sim, debt, evo)
    assert isinstance(prop, SynthesisProposal)
    assert prop.simulation_ok is True
    assert prop.confidence == 1.0  # 0.5 + 0.3 + 0.2
    assert prop.proposed_adr_id == "ADR-TBD-boundary"
    assert "Harden boundaries" in prop.change_request
    assert prop.title.startswith("Synthesized proposal:")


def test_simulation_violation_lowers_confidence_and_flags():
    sim = _FakeSimulator(ok=False)
    debt = _FakeDebt(score=0.1)
    evo = _FakeEvolution([])
    prop = ArchitectureSynthesizer().synthesize(sim, debt, evo)
    assert prop.simulation_ok is False
    assert prop.confidence == 0.5  # base only (no roadmap bonus)
    assert "forbidden import" in (prop.simulation.predicted_violations[0])


def test_empty_debt_and_roadmap_base_confidence():
    sim = _FakeSimulator(ok=True)
    debt = _FakeDebt(score=0.0, items=[])
    evo = _FakeEvolution([])
    prop = ArchitectureSynthesizer().synthesize(sim, debt, evo)
    # 0.5 base + 0.3 (sim ok) + 0.0 (no roadmap) == 0.8
    assert prop.confidence == 0.8
    assert prop.change_request == ""  # nothing to propose
    assert prop.proposed_adr_id == "ADR-TBD-synth"


def test_change_request_folds_high_debt_and_roadmap():
    sim = _FakeSimulator(ok=True)
    from contracts.i_architecture_intelligence import DebtItem
    debt = _FakeDebt(items=[
        DebtItem(area="drift", severity="high", detail="avg drift 0.9",
                 evidence="telemetry"),
        DebtItem(area="adr-lifecycle", severity="low",
                 detail="ADR-50 proposed", evidence="adrs.yaml"),
    ], score=0.6)
    evo = _FakeEvolution([RoadmapItem(title="Improve recovery",
                                      rationale="circuit 7/24h",
                                      priority="medium",
                                      proposed_adr="ADR-TBD-recovery")])
    prop = ArchitectureSynthesizer().synthesize(sim, debt, evo)
    # only high-severity debt must appear in change_request
    assert "avg drift 0.9" in prop.change_request
    assert "ADR-50 proposed" not in prop.change_request
    assert "Improve recovery" in prop.change_request


def test_none_engines_raise():
    with pytest.raises(TypeError):
        ArchitectureSynthesizer().synthesize(None, None, None)
