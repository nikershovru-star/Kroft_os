"""Negative tests for the architecture gate (WP-02, TZ-001).

Each test proves that a detector FIRES on an intentional violation fixture.
This is the Evidence that the gate is not a green lights — it actually catches
K1/K3/K6/K8 and F1 violations.

Fixtures live in tests/fixtures_violations/ and are NOT scanned by the
positive gate (they sit under tests/, outside PROJECT_PKGS).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from tests._repo_root import repo_root

ROOT = repo_root()
FIX = ROOT / "tests" / "fixtures_violations"

# Import detector helpers from the positive gate module.
from tests.common.test_architecture import (
    _check_file_imports,
    _file_package,
    _find_concrete_wiring_instantiation,
    ALLOWED,
    PROJECT_PKGS,
)


def _violations_for(fixture_name: str):
    path = FIX / fixture_name
    pkg, violations = _check_file_imports(path)
    return violations


def test_negative_k1_kernel_imports_infra():
    """Detector must catch kernel -> infrastructure import."""
    v = _violations_for("violation_k1_kernel_infra.py")
    assert any(dep == "infrastructure" for dep, _ in v), f"K1 detector missed infra import: {v}"


def test_negative_k6_adapters_imports_policies():
    """Detector must catch adapters -> policies import (V3 regression guard)."""
    v = _violations_for("violation_k6_adapters_policies.py")
    assert any(dep == "policies" for dep, _ in v), f"K6 detector missed policies import: {v}"


def test_negative_k3_kernel_instantiates_container():
    """Detector must catch kernel instantiating DependencyContainer."""
    path = FIX / "violation_k3_kernel_instantiate.py"
    found = _find_concrete_wiring_instantiation(path)
    assert any(cls == "DependencyContainer" for cls, _ in found), f"K3 detector missed: {found}"


def test_negative_k8_kernel_imports_ai():
    """Detector must catch kernel -> akb/research/llm import (K8/F4)."""
    path = FIX / "violation_k8_kernel_ai.py"
    tree = __import__("ast").parse(path.read_text(encoding="utf-8"))
    import ast
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
    assert any(m.split(".")[0] in ("akb", "research", "llm", "omni_route") for m in mods), \
        f"K8 detector missed AI import: {mods}"


def test_negative_f1_recovery_blocking_sleep():
    """Detector must catch blocking time.sleep() in recovery context."""
    import re
    path = FIX / "violation_f1_recovery_sleep.py"
    text = path.read_text(encoding="utf-8")
    assert re.search(r"time\.sleep\s*\(", text), "F1 detector missed blocking sleep"


def test_positive_gate_still_passes_on_real_code():
    """Sanity: the real codebase still passes the import-axis gate."""
    all_v = []
    for pkg in PROJECT_PKGS:
        d = ROOT / pkg
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            _, v = _check_file_imports(py)
            all_v.extend(v)
    assert not all_v, f"Positive gate regressed: {all_v}"
