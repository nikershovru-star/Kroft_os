"""Stage 7.7 - Architecture dependency-axis gate (static AST check).

Enforces the hexagonal dependency contract:
  contracts.*       -> stdlib only
  infrastructure.*  -> contracts + stdlib
  kernel.*          -> contracts, infrastructure, runtime + stdlib (NEVER adapters)
  runtime.*         -> contracts + stdlib
  adapters.*        -> contracts + stdlib
"""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PROJECT_PKGS = {"contracts", "infrastructure", "kernel", "runtime", "adapters"}

ALLOWED = {
    "contracts": set(),
    "infrastructure": {"contracts"},
    "kernel": {"contracts", "infrastructure", "runtime"},
    "runtime": {"contracts"},
    "adapters": {"contracts"},
}

STDLIB_BASES = {
    "os", "sys", "pathlib", "typing", "abc", "enum", "functools", "dataclasses",
    "collections", "json", "time", "re", "contextlib", "threading", "asyncio",
    "itertools", "copy", "math", "uuid", "datetime", "warnings", "logging",
}


def _file_package(path: Path) -> str:
    rel = path.relative_to(ROOT)
    return rel.parts[0]


def _imported_project_packages(node: ast.AST, file_pkg: str):
    """Yield project package names this import node depends on."""
    if isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
            # relative import -> same package (always allowed)
            return
        if node.module is None:
            return
        top = node.module.split(".")[0]
        if top in PROJECT_PKGS:
            yield top
    elif isinstance(node, ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in STDLIB_BASES:
                continue
            if top in PROJECT_PKGS:
                yield top


def _check_file(path: Path):
    pkg = _file_package(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for dep in _imported_project_packages(node, pkg):
                allowed = ALLOWED.get(pkg, set())
                if dep not in allowed:
                    violations.append((dep, node.lineno))
    return pkg, violations


def test_no_forbidden_cross_layer_imports():
    all_violations = []
    scanned = 0
    for pkg in PROJECT_PKGS:
        pkg_dir = ROOT / pkg
        if not pkg_dir.exists():
            continue
        for py in pkg_dir.rglob("*.py"):
            scanned += 1
            pkg_name, violations = _check_file(py)
            for dep, lineno in violations:
                all_violations.append(
                    f"{py.relative_to(ROOT)}:{lineno} "
                    f"package '{pkg_name}' illegally imports '{dep}' "
                    f"(allowed: {sorted(ALLOWED.get(pkg_name, set()))})"
                )
    assert not all_violations, (
        "ARCHITECTURE GATE FAILED - forbidden dependencies found:\n"
        + "\n".join(all_violations)
    )
    assert scanned > 0


def test_each_layer_respects_its_axis():
    # Explicit, readable per-layer assertion.
    expectations = {
        "contracts": set(),
        "infrastructure": {"contracts"},
        "kernel": {"contracts", "infrastructure", "runtime"},
        "runtime": {"contracts"},
        "adapters": {"contracts"},
    }
    for pkg, expected in expectations.items():
        assert ALLOWED[pkg] == expected
