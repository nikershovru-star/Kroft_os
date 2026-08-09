"""Architecture Intelligence ports (WP-12, ADR-042).

K1-compliant: stdlib only. Three capabilities formalizing the architect agent's
reasoning as KROFT-native services (reuse AKB, not runtime code — LAW K8):
- L5 Simulator: predict impact of a change before commit (dry-run + axis check)
- L6 Tech Debt Engine: audit architectural debt from AKB + telemetry metrics
- L7 Evolution Engine: generate refactor roadmap from drift + circuit trends
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# --- L5 Simulator ---------------------------------------------------------

@dataclass
class SimulationResult:
    ok: bool
    predicted_violations: List[str] = field(default_factory=list)
    notes: str = ""


class IChangeSimulator(ABC):
    """Predicts impact of a code change without applying it."""

    @abstractmethod
    def simulate_imports(self, files: List[str]) -> SimulationResult:
        """Check that files still import only allowed layers (K1/K8 preview)."""

    @abstractmethod
    def dry_run_command(self, command: List[str]) -> SimulationResult:
        """Run a non-mutating preview (e.g. py_compile) via sandbox."""


# --- L6 Tech Debt Engine --------------------------------------------------

@dataclass
class DebtItem:
    area: str
    severity: str  # "low" | "medium" | "high"
    detail: str
    evidence: str = ""


@dataclass
class DebtReport:
    score: float  # 0.0 (clean) .. 1.0 (heavy debt)
    items: List[DebtItem] = field(default_factory=list)
    generated_at: str = ""

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.items if i.severity == "high")


class ITechDebtAuditor(ABC):
    """Audits architectural debt from AKB rules + telemetry metrics."""

    @abstractmethod
    def audit(self) -> DebtReport:
        ...


# --- L7 Evolution Engine -------------------------------------------------

@dataclass
class RoadmapItem:
    title: str
    rationale: str
    priority: str  # "low" | "medium" | "high"
    proposed_adr: Optional[str] = None


@dataclass
class EvolutionRoadmap:
    items: List[RoadmapItem] = field(default_factory=list)
    generated_at: str = ""


class IEvolutionPlanner(ABC):
    """Generates a refactor/evolution roadmap from drift + circuit trends."""

    @abstractmethod
    def plan(self) -> EvolutionRoadmap:
        ...


# --- L8 Architecture Synthesizer --------------------------------------------

@dataclass
class SynthesisProposal:
    """A consolidated ADR proposal joining L5/L6/L7 outputs (ADR-0XX)."""
    title: str
    summary: str
    proposed_adr_id: str
    change_request: str
    simulation: Optional[SimulationResult] = None
    debt: Optional[DebtReport] = None
    roadmap: Optional[EvolutionRoadmap] = None
    confidence: float = 0.0          # 0.0 (weak) .. 1.0 (strong)
    simulation_ok: bool = True
    generated_at: str = ""


class IArchitectureSynthesizer(ABC):
    """L8: joins simulator + debt + evolution into one ADR proposal (KB-Update loop)."""

    @abstractmethod
    def synthesize(self, simulator: "IChangeSimulator",
                   debt_engine: "ITechDebtAuditor",
                   evolution_engine: "IEvolutionPlanner") -> SynthesisProposal:
        """Fold L5/L6/L7 outputs into a single SynthesisProposal."""

