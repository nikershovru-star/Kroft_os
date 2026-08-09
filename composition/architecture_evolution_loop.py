"""Architecture Evolution Loop — closes the L5->L8 research/synthesis cycle (ADR-0XX).

Composition-root module (K5-legal: cross-layers services+contracts+kernel here).
Connects the autonomous research scheduler (L8 self-set goals) with the
architecture synthesizer (L8 ADR proposal) into one deterministic cycle so the
maturity ladder's loop "research -> synthesize -> ADR -> KB-Update" is closed.

Deterministic (I-09): run_cycle(n) performs n scheduler ticks + one synthesis,
with NO real sleep/timers. Real cron scheduling is a separate TZ.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from contracts.i_architecture_intelligence import (
    IArchitectureSynthesizer,
    SynthesisProposal,
)
from contracts.i_agent_platform import IResearchScheduler, ResearchFinding


class ArchitectureEvolutionLoop:
    """Ties L8 scheduler + L8 synthesizer into one autonomous cycle (ADR-0XX)."""

    def __init__(
        self,
        scheduler: IResearchScheduler,
        synthesizer: IArchitectureSynthesizer,
        simulator=None,
        debt_engine=None,
        evolution_engine=None,
    ) -> None:
        if scheduler is None or synthesizer is None:
            raise TypeError("ArchitectureEvolutionLoop requires scheduler + synthesizer instances")
        self._scheduler = scheduler
        self._synthesizer = synthesizer
        self._simulator = simulator
        self._debt_engine = debt_engine
        self._evolution_engine = evolution_engine

    def run_cycle(self, n: int = 1) -> Tuple[List[ResearchFinding], SynthesisProposal]:
        """Run n research ticks, then synthesize a proposal from L5/L6/L7.

        Returns (findings, proposal). The proposal's confidence reflects the
        current repo health; the findings feed the eventual KB-Update.
        """
        findings = self._scheduler.run_for(n)
        proposal = self._synthesizer.synthesize(
            self._simulator, self._debt_engine, self._evolution_engine
        )
        return findings, proposal

    def findings(self) -> List[ResearchFinding]:
        return self._scheduler.findings()
