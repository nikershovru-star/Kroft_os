"""Architecture Intelligence services (WP-12, ADR-042).

K8-compliant: services/ only, imports contracts + stdlib. L5/L6/L7 formalize the
architect agent's reasoning as KROFT-native components that reuse the AKB YAML
layer (laws/adrs/history/import_matrix) and telemetry metrics — NOT runtime code.

L5 Simulator       — dry-run import/axis preview via IExecutionSandbox.
L6 Tech Debt Engine — AKB-rule audit + telemetry metrics -> DebtReport.
L7 Evolution Engine — drift + circuit trends -> refactor roadmap.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts.i_architecture_intelligence import (
    DebtItem,
    DebtReport,
    EvolutionRoadmap,
    IArchitectureSynthesizer,
    IChangeSimulator,
    IEvolutionPlanner,
    ITechDebtAuditor,
    RoadmapItem,
    SimulationResult,
    SynthesisProposal,
)
from contracts.i_execution_sandbox import IExecutionSandbox
from contracts.i_telemetry import ITelemetrySink


_AKB_LAYER_RE = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)")


def _package_of(path: str) -> str:
    """Best-effort layer guess from a file path (kernel/ runtime/ services/ ...)."""
    p = Path(path).as_posix().lower()
    for layer in ("kernel", "runtime", "services", "adapters", "infrastructure",
                 "policies", "composition", "contracts", "plugins", "cli"):
        if f"/{layer}/" in p or p.startswith(f"{layer}/"):
            return layer
    return "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArchitectureSimulator(IChangeSimulator):
    """L5: predict import-layer violations before applying a change."""

    def __init__(self, sandbox: Optional[IExecutionSandbox] = None,
                 allowed_layers: Optional[Dict[str, List[str]]] = None) -> None:
        self._sandbox = sandbox
        # default K1/K8 axis: kernel may import only contracts+stdlib
        self._allowed = allowed_layers or {
            "kernel": ["contracts", "__future__", "typing", "dataclasses", "enum",
                       "abc", "os", "sys", "re", "pathlib", "datetime", "time",
                       "json", "collections", "functools", "itertools", "threading"],
            "runtime": ["contracts", "kernel", "__future__", "typing", "dataclasses",
                        "enum", "abc", "os", "sys", "re", "pathlib", "datetime",
                        "time", "json", "collections", "functools", "itertools", "threading"],
        }

    def simulate_imports(self, files: List[str]) -> SimulationResult:
        violations: List[str] = []
        for f in files:
            pkg = _package_of(f)
            allowed = set()
            for layer, mods in self._allowed.items():
                if pkg == layer or pkg.startswith(layer + "."):
                    allowed = set(mods)
                    break
            for line in Path(f).read_text(encoding="utf-8", errors="ignore").splitlines():
                m = _AKB_LAYER_RE.match(line)
                if not m:
                    continue
                top = m.group(1).split(".")[0]
                if top in ("__future__", "typing", "dataclasses", "enum", "abc"):
                    continue
                if allowed and top not in allowed:
                    violations.append(f"{f}: forbidden import '{top}' (layer {pkg})")
        return SimulationResult(ok=not violations, predicted_violations=violations,
                                 notes="static import-axis preview (predictive, not runtime)")

    def dry_run_command(self, command: List[str]) -> SimulationResult:
        if self._sandbox is None:
            return SimulationResult(ok=False, predicted_violations=["no sandbox wired"],
                                    notes="dry-run requires IExecutionSandbox")
        res = self._sandbox.execute(command, timeout_sec=30.0)
        return SimulationResult(ok=res.returncode == 0,
                                predicted_violations=[] if res.returncode == 0 else [res.stderr[:200]],
                                notes=f"returncode={res.returncode}")


class TechDebtEngine(ITechDebtAuditor):
    """L6: audit debt from AKB rules + telemetry metrics."""

    def __init__(self, akb_path: str, telemetry: Optional[ITelemetrySink] = None) -> None:
        self._akb = Path(akb_path)
        self._telemetry = telemetry

    def audit(self) -> DebtReport:
        items: List[DebtItem] = []
        items += self._check_stale_adrs()
        items += self._check_drift_metric()
        items += self._check_circuit_metric()
        score = self._score(items)
        return DebtReport(score=score, items=items, generated_at=_now())

    def _check_stale_adrs(self) -> List[DebtItem]:
        adrs_file = self._akb / "adrs.yaml"
        if not adrs_file.exists():
            return []
        import yaml
        data = yaml.safe_load(adrs_file.read_text(encoding="utf-8")) or {}
        stale = [a for a in data.get("adrs", [])
                 if a.get("status") in ("proposed", "under_review")]
        out = []
        for a in stale:
            out.append(DebtItem(area="adr-lifecycle", severity="low",
                                detail=f"ADR {a.get('id')} still {a.get('status')}",
                                evidence="adrs.yaml"))
        return out

    def _check_drift_metric(self) -> List[DebtItem]:
        if self._telemetry is None:
            return []
        agg = self._telemetry.aggregate("drift.score", 3600.0)
        if agg["count"] >= 1 and agg["avg"] > 0.5:
            return [DebtItem(area="drift", severity="high" if agg["avg"] > 0.8 else "medium",
                             detail=f"avg drift.score {agg['avg']:.2f} over {int(agg['count'])} samples",
                             evidence="ITelemetrySink.drift.score")]
        return []

    def _check_circuit_metric(self) -> List[DebtItem]:
        if self._telemetry is None:
            return []
        agg = self._telemetry.aggregate("circuit.trip", 3600.0)
        if agg["count"] >= 5:
            return [DebtItem(area="recovery", severity="medium",
                             detail=f"circuit.trip rate {int(agg['count'])}/hr",
                             evidence="ITelemetrySink.circuit.trip")]
        return []

    @staticmethod
    def _score(items: List[DebtItem]) -> float:
        weights = {"low": 0.1, "medium": 0.3, "high": 0.6}
        raw = sum(weights.get(i.severity, 0.1) for i in items)
        return min(1.0, raw)


class EvolutionEngine(IEvolutionPlanner):
    """L7: roadmap from drift + circuit trends (telemetry) + AKB history."""

    def __init__(self, akb_path: str, telemetry: Optional[ITelemetrySink] = None,
                 debt_engine: Optional[ITechDebtAuditor] = None) -> None:
        self._akb = Path(akb_path)
        self._telemetry = telemetry
        self._debt = debt_engine

    def plan(self) -> EvolutionRoadmap:
        items: List[RoadmapItem] = []
        if self._telemetry is not None:
            drift = self._telemetry.aggregate("drift.score", 86400.0)
            if drift["count"] >= 1 and drift["avg"] > 0.5:
                items.append(RoadmapItem(
                    title="Harden K1/K8 boundaries (drift detected)",
                    rationale=f"avg drift.score {drift['avg']:.2f} over {int(drift['count'])}d",
                    priority="high" if drift["avg"] > 0.8 else "medium",
                    proposed_adr="ADR-TBD-boundary",
                ))
            circ = self._telemetry.aggregate("circuit.trip", 86400.0)
            if circ["count"] >= 5:
                items.append(RoadmapItem(
                    title="Improve agent recovery thresholds",
                    rationale=f"circuit.trip {int(circ['count'])}/24h",
                    priority="medium", proposed_adr="ADR-TBD-recovery",
                ))
        if self._debt is not None:
            report = self._debt.audit()
            if report.high_count > 0:
                items.append(RoadmapItem(
                    title="Resolve high-severity architecture debt",
                    rationale=f"{report.high_count} high-severity debt items (score {report.score:.2f})",
                    priority="high", proposed_adr="ADR-TBD-debt",
                ))
        return EvolutionRoadmap(items=items, generated_at=_now())


class ArchitectureSynthesizer(IArchitectureSynthesizer):
    """L8: fold L5/L6/L7 outputs into a single ADR proposal (ADR-0XX).

    Closes the research -> synthesize -> ADR -> KB-Update loop of the
    architecture-intelligence maturity ladder. Does NOT apply changes; it only
    proposes. K8-clean: services + contracts + stdlib (reuses AKB/telemetry,
    never runtime code).
    """

    def synthesize(self, simulator: "IChangeSimulator",
                   debt_engine: "ITechDebtAuditor",
                   evolution_engine: "IEvolutionPlanner") -> SynthesisProposal:
        if simulator is None or debt_engine is None or evolution_engine is None:
            raise TypeError("synthesize requires simulator, debt_engine, evolution_engine instances")
        sim = simulator.simulate_imports([])
        debt = debt_engine.audit()
        roadmap = evolution_engine.plan()

        simulation_ok = sim.ok
        roadmap_items = roadmap.items or []
        has_roadmap = len(roadmap_items) > 0

        # Confidence: base 0.5, +0.3 if simulation clean, +0.2 if a roadmap exists.
        confidence = 0.5
        if simulation_ok:
            confidence += 0.3
        if has_roadmap:
            confidence += 0.2
        confidence = max(0.0, min(1.0, confidence))

        proposed_adr_id = "ADR-TBD-synth"
        if has_roadmap and roadmap_items[0].proposed_adr:
            proposed_adr_id = roadmap_items[0].proposed_adr

        # change_request: textual fold of roadmap titles + high-severity debt.
        cr_parts: List[str] = []
        for it in roadmap_items:
            cr_parts.append(f"- {it.priority}: {it.title} (rationale: {it.rationale})")
        for d in debt.items:
            if d.severity == "high":
                cr_parts.append(f"- DEBT[high]: {d.detail} (evidence: {d.evidence})")
        change_request = "\n".join(cr_parts)

        title = "Synthesized architecture evolution proposal"
        if has_roadmap:
            title = f"Synthesized proposal: {roadmap_items[0].title}"

        summary = (
            f"sim_ok={simulation_ok} debt_score={debt.score:.2f} "
            f"roadmap_items={len(roadmap_items)} confidence={confidence:.2f}"
        )

        return SynthesisProposal(
            title=title,
            summary=summary,
            proposed_adr_id=proposed_adr_id,
            change_request=change_request,
            simulation=sim,
            debt=debt,
            roadmap=roadmap,
            confidence=confidence,
            simulation_ok=simulation_ok,
            generated_at=_now(),
        )
