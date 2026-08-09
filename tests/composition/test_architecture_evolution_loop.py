"""Loop-closure proof-of-fire: ArchitectureEvolutionLoop (ADR-0XX).

Self-contained — NO Ollama. Fake scheduler + fake synthesizer prove the loop
joins research findings with a synthesis proposal and degrades gracefully.

Proves:
  - run_cycle(2) returns (2 findings, non-empty proposal with confidence>0)
  - loop does not lose scheduler findings (findings() equals what run_cycle saw)
  - None scheduler/synthesizer -> TypeError
  - determinism: run_cycle(1) twice -> stable finding count
"""
from __future__ import annotations

from typing import List, Optional

import pytest

from contracts.i_agent_platform import ResearchFinding
from contracts.i_architecture_intelligence import SynthesisProposal
from composition.architecture_evolution_loop import ArchitectureEvolutionLoop


class _FakeScheduler:
    def __init__(self, findings):
        self._f = findings
        self._history: List[ResearchFinding] = []
    def run_for(self, n):
        out = self._f[:n]
        self._history.extend(out)
        return out
    def findings(self):
        return list(self._history)


class _FakeSynthesizer:
    def __init__(self, proposal):
        self._p = proposal
    def synthesize(self, simulator, debt_engine, evolution_engine):
        return self._p


def _mk_findings(n):
    return [ResearchFinding(goal=f"g{i}", answer="a", success=True, tick=i+1)
            for i in range(n)]

def _mk_proposal(conf=0.9):
    return SynthesisProposal(title="p", summary="s", proposed_adr_id="ADR-TBD",
                            change_request="x", confidence=conf)


def test_run_cycle_returns_findings_and_proposal():
    sched = _FakeScheduler(_mk_findings(3))
    synth = _FakeSynthesizer(_mk_proposal(0.9))
    loop = ArchitectureEvolutionLoop(sched, synth)
    findings, prop = loop.run_cycle(2)
    assert len(findings) == 2
    assert isinstance(prop, SynthesisProposal)
    assert prop.confidence > 0
    assert loop.findings() == findings  # not lost


def test_none_instances_raise():
    with pytest.raises(TypeError):
        ArchitectureEvolutionLoop(None, _FakeSynthesizer(_mk_proposal()))
    with pytest.raises(TypeError):
        ArchitectureEvolutionLoop(_FakeScheduler(_mk_findings(1)), None)


def test_determinism():
    a = ArchitectureEvolutionLoop(_FakeScheduler(_mk_findings(2)), _FakeSynthesizer(_mk_proposal()))
    b = ArchitectureEvolutionLoop(_FakeScheduler(_mk_findings(2)), _FakeSynthesizer(_mk_proposal()))
    assert len(a.run_cycle(1)[0]) == len(b.run_cycle(1)[0]) == 1
