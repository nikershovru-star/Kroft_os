"""Runtime self-analysis engine (TZ-AGENT-001 WP-05, ADR-037 §2, K8).

K8 meta-layer: lives in services/self_analysis/ (NOT kernel/ or runtime/).
Provides health_check() (agent states, pool limits, K1 snapshot) and
detect_drift() (import_matrix.yaml vs actual imports in kernel/ + runtime/).
K1-compliant imports (contracts + stdlib only).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from contracts.agent_orchestration import (
    AgentState,
    DriftRecord,
    HealthReport,
    IAgentLifecycle,
    ISelfAnalyzer,
)
from contracts import IEventBus


# Allowed import targets per scanned package (single source of truth:
# docs/architecture/AKB/import_matrix.yaml). Mirrors the arch-gate matrix.
_DEFAULT_MATRIX: Dict[str, List[str]] = {
    "kernel": ["contracts", "runtime"],
    "runtime": ["contracts"],
    "services": ["contracts"],
}


class SelfAnalyzer(ISelfAnalyzer):
    """Introspects runtime health and architecture drift (K8 meta-layer)."""

    def __init__(
        self,
        lifecycle: IAgentLifecycle,
        root: Path,
        matrix_path: Optional[Path] = None,
        bus: Optional["IEventBus"] = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._root = Path(root)
        self._matrix_path = matrix_path or (
            self._root / "docs" / "architecture" / "AKB" / "import_matrix.yaml"
        )
        self._bus = bus

    # -- ISelfAnalyzer -----------------------------------------------------

    def health_check(self) -> HealthReport:
        agents: Dict[str, str] = {}
        stale = False
        for agent_id in self._lifecycle.list_agents():
            state = self._lifecycle.get_state(agent_id)
            if state is None:
                continue
            agents[agent_id] = state.value
            if state is AgentState.STALE:
                stale = True
        k1_ok = self._k1_snapshot_ok()
        if not k1_ok:
            status = "red"
        elif stale:
            status = "yellow"
        else:
            status = "green"
        return HealthReport(status=status, agents=agents, drifts=[])

    def detect_drift(self) -> List[DriftRecord]:
        matrix = self._load_matrix()
        # Q5: drift scope = kernel/ + runtime/ only (where K1/K8 are critical).
        scan_pkgs = {"kernel", "runtime"}
        drifts: List[DriftRecord] = []
        # project packages that, if imported cross-boundary, count as drift
        known_pkgs = set(matrix.keys()) | {
            "contracts", "kernel", "runtime", "services", "adapters",
            "infrastructure", "policies", "plugins", "composition", "cli",
        }
        for pkg in scan_pkgs:
            allowed = matrix.get(pkg, [])
            pkg_dir = self._root / pkg
            if not pkg_dir.is_dir():
                continue
            for py in sorted(pkg_dir.rglob("*.py")):
                if "__pycache__" in str(py):
                    continue
                rel = str(py.relative_to(self._root)).replace("\\", "/")
                for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                    target = self._import_target(line)
                    if target is None:
                        continue
                    if target == pkg:  # self-package import is always legal
                        continue
                    # only project-to-project boundary violations are drift;
                    # stdlib / third-party imports are out of scope (R2).
                    if target not in known_pkgs:
                        continue
                    if target not in allowed and not target.startswith("__"):
                        drifts.append(DriftRecord(
                            file=rel, line=lineno, rule=f"{pkg}->{target}",
                            actual_import=line.strip(),
                        ))
        self._publish_drift(drifts)
        return drifts

    # -- helpers -----------------------------------------------------------

    def _publish_drift(self, drifts: List[DriftRecord]) -> None:
        if self._bus is None or not drifts:
            return
        # score = normalized count (capped) as a simple confidence proxy
        score = min(1.0, len(drifts) / 20.0)
        self._bus.publish_sync("self.drift", {
            "score": score, "count": len(drifts),
            "files": [d.file for d in drifts[:5]],
        })

    def _k1_snapshot_ok(self) -> bool:
        """Quick K1 check: kernel/ must not import services/ or adapters/."""
        kernel = self._root / "kernel"
        if not kernel.is_dir():
            return True
        bad = re.compile(r"^\s*(from|import)\s+(services|adapters|infrastructure)\b")
        for py in kernel.rglob("*.py"):
            if "__pycache__" in str(py):
                continue
            for line in py.read_text(encoding="utf-8").splitlines():
                if bad.match(line):
                    return False
        return True

    def _load_matrix(self) -> Dict[str, List[str]]:
        try:
            data = yaml.safe_load(self._matrix_path.read_text(encoding="utf-8"))
            return dict(data.get("matrix", _DEFAULT_MATRIX))
        except FileNotFoundError:
            return dict(_DEFAULT_MATRIX)

    @staticmethod
    def _import_target(line: str) -> Optional[str]:
        m = re.match(r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)", line)
        if not m:
            return None
        top = m.group(1).split(".")[0]
        # ignore stdlib / relative imports
        if top in ("__future__", "typing", "dataclasses", "enum", "abc",
                   "os", "sys", "re", "pathlib", "datetime", "time", "json",
                   "yaml", "collections", "functools", "itertools", "threading"):
            return None
        return top
