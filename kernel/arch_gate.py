"""AKB Runtime Verification Gate — lightweight runtime + CI enforcement.

Scope (K1/K3/K6/K8):
- kernel/ may import contracts/ + runtime/ only.
- services/, adapters/, infrastructure/, policies/, plugins/, cli/ may import contracts/ only.
- composition/ may import anything.
- tests/ are EXCLUDED from enforcement.

This module is K1-compliant: stdlib + contracts only.
It is intended to be called from CLI/CI, NOT from hot runtime paths.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

PROJECT_PKGS = (
    "contracts",
    "infrastructure",
    "kernel",
    "runtime",
    "services",
    "adapters",
    "policies",
    "plugins",
    "composition",
    "cli",
)

ROOT = Path(__file__).resolve().parent.parent


def _akb_for(root: Path) -> Path:
    return root / "docs" / "architecture" / "AKB"


class GateViolation(Exception):
    """Single architecture gate violation."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.message = message


def _load_yaml(path: Path):
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise GateViolation(str(path), f"YAML parse error: {exc}") from exc


def _pkg_for(path: Path) -> Optional[str]:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if parts and parts[0] in PROJECT_PKGS:
        return parts[0]
    if parts[:2] == ("kernel", "security"):
        return "kernel"
    if parts[:2] == ("kernel", "tenant"):
        return "kernel"
    if parts[:2] == ("services", "security"):
        return "services"
    if parts[:2] == ("services", "tenant"):
        return "services"
    if parts[:2] == ("services", "agent_orchestration"):
        return "services"
    if parts[:2] == ("services", "model_router"):
        return "services"
    if parts[:2] == ("services", "knowledge_graph"):
        return "services"
    if parts[:2] == ("services", "self_analysis"):
        return "services"
    if parts[:2] == ("services", "factcheck"):
        return "services"
    if parts[:2] == ("contracts", "security"):
        return "contracts"
    if parts[:2] == ("contracts", "tenant"):
        return "contracts"
    if parts[:2] == ("contracts", "knowledge_graph"):
        return "contracts"
    if parts[:2] == ("contracts", "agent_orchestration"):
        return "contracts"
    if parts[:2] == ("adapters", "exporters"):
        return "adapters"
    return None


def _allowed_for(pkg: str, matrix: Dict[str, List[str]]) -> List[str]:
    return list(matrix.get("matrix", {}).get(pkg, []))


def _stdlib_bases(matrix: Dict[str, List[str]]) -> List[str]:
    return list(matrix.get("stdlib_bases", []))


def _imports_in(path: Path) -> List[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return imports


def _is_project_import(name: str) -> bool:
    return name in PROJECT_PKGS


def _is_stdlib(name: str, stdlib_bases: List[str]) -> bool:
    if name in stdlib_bases:
        return True
    return False


def _is_self(pkg: str, name: str, path: Path) -> bool:
    if name != pkg:
        return False
    rel = path.relative_to(ROOT)
    if rel.parts[0] == name:
        return True
    return False


def scan(matrix: Dict[str, List[str]], stdlib_bases: List[str]) -> List[GateViolation]:
    violations: List[GateViolation] = []
    for pkg in PROJECT_PKGS:
        for path in (ROOT / pkg).rglob("*.py"):
            if "tests" in path.parts:
                continue
            pkg_name = _pkg_for(path) or pkg
            if pkg_name != pkg:
                continue
            allowed = _allowed_for(pkg, matrix) + [pkg] + ["__future__"] + list(stdlib_bases)
            for imp in _imports_in(path):
                if not _is_project_import(imp):
                    continue
                if _is_stdlib(imp, stdlib_bases):
                    continue
                if _is_self(pkg, imp, path):
                    continue
                if imp in allowed:
                    continue
                violations.append(GateViolation(
                    str(path.relative_to(ROOT)),
                    f"{pkg} -> {imp} not allowed by import_matrix.yaml",
                ))
    return violations


def _check_k1(caps: Dict[str, List[str]]) -> List[GateViolation]:
    violations: List[GateViolation] = []
    for path in (ROOT / "kernel").rglob("*.py"):
        if "tests" in path.parts:
            continue
        for imp in _imports_in(path):
            if imp in {"contracts", "runtime", "__future__"}:
                continue
            if imp in caps.get("stdlib_bases", []):
                continue
            if imp == "kernel":
                continue
            if imp in {"security", "tenant"}:
                continue
            if imp in PROJECT_PKGS and imp != "contracts" and imp != "runtime":
                violations.append(GateViolation(
                    str(path.relative_to(ROOT)),
                    f"K1 violation: kernel/ imports '{imp}' (allowed: contracts/runtime only)",
                ))
    return violations


def run() -> Tuple[int, List[GateViolation]]:
    matrix_path = _akb_for(ROOT) / "import_matrix.yaml"
    if not matrix_path.exists():
        return 1, [GateViolation(str(matrix_path), "AKB import_matrix.yaml missing")]

    matrix = _load_yaml(matrix_path)
    stdlib_bases = _stdlib_bases(matrix)
    violations: List[GateViolation] = []

    try:
        violations.extend(_check_k1(matrix))
    except GateViolation as exc:
        violations.append(exc)

    violations.extend(scan(matrix, stdlib_bases))

    if violations:
        for v in violations:
            print(f"[AKB-GATE] {v.path}: {v.message}")
        return 1, violations

    print("[AKB-GATE] PASSED")
    return 0, []


if __name__ == "__main__":
    import sys
    sys.exit(run()[0])
