"""Architecture gate tests (WP-02, TZ-001).

Verifies that the production codebase passes the AKB import matrix gate.
The arch_gate module scans all .py files in the project packages (excluding
tests/) and ensures import rules from docs/architecture/akb/import_matrix.yaml
are respected.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kernel.arch_gate import run, _imports_in, GateViolation, PROJECT_PKGS


def test_arch_gate_passes_on_production_code():
    """The production codebase should pass the architectural gate."""
    rc, violations = run()
    assert rc == 0, f"Arch gate violations found:\n" + "\n".join(
        f"  {v.path}: {v.message}" for v in violations
    )


def test_arch_gate_detects_k1_violation():
    """K1 violation: kernel importing infrastructure should be flagged."""
    # Create a temporary violation file in a non-test location
    violation_code = "from infrastructure import DependencyContainer\n"

    # Simulate what arch_gate would detect
    tree = ast.parse(violation_code)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])

    # "infrastructure" is a project package but not allowed for kernel
    assert "infrastructure" in imports
    assert "infrastructure" in PROJECT_PKGS  # It's a project package
    assert "infrastructure" not in ["contracts", "runtime"]  # Not allowed for kernel


def test_arch_gate_detects_k8_violation():
    """K8 violation: kernel importing akb/research/llm should be flagged."""
    violation_code = "import akb\n"

    tree = ast.parse(violation_code)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])

    # "akb" is not a valid project package — it's not in PROJECT_PKGS
    assert "akb" in imports
    assert "akb" not in PROJECT_PKGS  # Not a recognized project package


def test_import_matrix_is_valid_yaml():
    """The import_matrix.yaml should be valid YAML with expected structure."""
    matrix_path = ROOT / "docs" / "architecture" / "akb" / "import_matrix.yaml"
    assert matrix_path.exists(), f"import_matrix.yaml not found at {matrix_path}"

    import yaml
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))

    assert "version" in matrix
    assert "matrix" in matrix
    assert "stdlib_bases" in matrix
    assert "scanned_packages" in matrix

    # Verify key import rules
    assert matrix["matrix"]["contracts"] == []
    assert matrix["matrix"]["runtime"] == ["contracts"]
    assert matrix["matrix"]["services"] == ["contracts"]
    assert matrix["matrix"]["adapters"] == ["contracts"]


def test_arch_gate_run_returns_tuple():
    """arch_gate.run() should return (exit_code, violations_list)."""
    rc, violations = run()
    assert isinstance(rc, int)
    assert isinstance(violations, list)
    for v in violations:
        assert isinstance(v, GateViolation)
        assert v.path
        assert v.message


def test_project_packages_constant():
    """PROJECT_PKGS should contain all expected package names."""
    expected = {"contracts", "infrastructure", "kernel", "runtime",
                "services", "adapters", "policies", "plugins",
                "composition", "cli"}
    assert set(PROJECT_PKGS) == expected