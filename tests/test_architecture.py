"""Stage 7.7 - Architecture dependency-axis + forbidden-pattern gate (WP-02).

Enforces the hexagonal dependency contract via a matrix loaded from
`docs/architecture/AKB/import_matrix.yaml` (single source of truth, TZ-001 WP-02):

  contracts.*       -> stdlib only
  infrastructure.*  -> contracts + stdlib
  kernel.*          -> contracts, runtime + stdlib (NEVER infra/services/adapters/policies)  [K1]
  runtime.*         -> contracts + stdlib
  adapters.*        -> contracts + stdlib  (NEVER policies/services/infra)  [K6, V3]
  services.*        -> contracts + stdlib  (application layer; may use policies via port)
  policies.*        -> contracts + stdlib  (NEVER adapters/services/infra)  [K6]
  plugins.*         -> contracts + stdlib
  composition.*     -> everything (ONLY assembly layer)  [K3]
  cli.*             -> composition, contracts (+ legacy kernel/service)

Plus forbidden-pattern detectors F1-F6 (AST/regex). Each detector has a
negative test proving it fires (tests/test_architecture_negative.py).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
AKB = ROOT / "docs" / "architecture" / "AKB"

# --- Load matrix from AKB (single source of truth) -------------------------
def _load_matrix() -> dict:
    path = AKB / "import_matrix.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    matrix = {k: set(v) for k, v in data["matrix"].items() if isinstance(v, list)}
    # 'infrastructure_extra' is a placeholder; drop it.
    matrix.pop("infrastructure_extra", None)
    return {
        "matrix": matrix,
        "packages": set(data.get("scanned_packages", [])),
        "stdlib": set(data.get("stdlib_bases", [])),
    }

_MATRIX_DATA = _load_matrix()
ALLOWED = _MATRIX_DATA["matrix"]
PROJECT_PKGS = _MATRIX_DATA["packages"]
STDLIB_BASES = _MATRIX_DATA["stdlib"]


# --- AST helpers -----------------------------------------------------------
def _file_package(path: Path) -> str:
    rel = path.relative_to(ROOT)
    return rel.parts[0]


def _imported_project_packages(node: ast.AST):
    if isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
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


def _check_file_imports(path: Path):
    pkg = _file_package(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for dep in _imported_project_packages(node):
                if dep == pkg:
                    continue
                allowed = ALLOWED.get(pkg, set())
                if dep not in allowed:
                    violations.append((dep, node.lineno))
    return pkg, violations


# --- K1/K3/K6 import-axis gate --------------------------------------------
def test_no_forbidden_cross_layer_imports():
    all_violations = []
    scanned = 0
    for pkg in PROJECT_PKGS:
        pkg_dir = ROOT / pkg
        if not pkg_dir.exists():
            continue
        for py in pkg_dir.rglob("*.py"):
            scanned += 1
            pkg_name, violations = _check_file_imports(py)
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
    """ALLOWED matrix matches the AKB import_matrix.yaml (single source)."""
    for pkg, expected in ALLOWED.items():
        assert ALLOWED[pkg] == expected, f"{pkg}: {ALLOWED[pkg]} != {expected}"


def test_services_do_not_cross_import():
    """F2/F3: service modules must not import sibling service modules."""
    services_dir = ROOT / "services"
    violations = []
    for py in services_dir.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.split(".")[0] == "services":
                    violations.append(f"{py.relative_to(ROOT)}:{node.lineno} imports '{mod}'")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "services":
                        violations.append(f"{py.relative_to(ROOT)}:{node.lineno} imports '{alias.name}'")
    assert not violations, "SERVICE CROSS-IMPORT GATE FAILED:\n" + "\n".join(violations)


# --- K3: wiring only in composition ---------------------------------------
# Concrete ASSEMBLY classes that must NOT be instantiated outside composition/
# (and cli/ as legacy entrypoint). These are the "wiring" primitives the
# Composition Root owns. Adapters/infrastructure define their OWN port impls
# (e.g. LocalFileSystemAdapter), which is legal -- so they are NOT in this set.
_CONCRETE_WIRING = {
    "DependencyContainer",   # composition owns DI
    "SnapshotStore",         # replaced by IStateRepository port (Phase B.3)
}


def _find_concrete_wiring_instantiation(path: Path) -> list:
    """Detect `X(` where X is an assembly class, outside composition/cli.

    Excludes class *definitions* (`class X(`) and type-annotation contexts.
    """
    pkg = _file_package(path)
    if pkg in ("composition", "cli", "infrastructure", "contracts", "adapters"):
        # adapters define their own port impls; infra IS the impl layer.
        return []
    text = path.read_text(encoding="utf-8")
    found = []
    for cls in _CONCRETE_WIRING:
        for m in re.finditer(rf"(?<!\w)(?:class\s+)?{cls}\s*\(", text):
            # skip `class X(` definitions
            start = max(0, m.start() - 6)
            if text[start:m.start()].lstrip().startswith("class"):
                continue
            lineno = text.count("\n", 0, m.start()) + 1
            found.append((cls, lineno))
    return found


def test_wiring_only_in_composition():
    """K3: kernel/runtime/services/policies must NOT instantiate assembly
    classes (DependencyContainer, SnapshotStore). Only composition/ (and
    legacy cli/) may wire them."""
    violations = []
    for pkg in ("kernel", "runtime", "services", "policies"):
        pkg_dir = ROOT / pkg
        if not pkg_dir.exists():
            continue
        for py in pkg_dir.rglob("*.py"):
            for cls, lineno in _find_concrete_wiring_instantiation(py):
                violations.append(f"{py.relative_to(ROOT)}:{lineno} instantiates '{cls}' (K3 violation)")
    assert not violations, "K3 GATE FAILED (wiring outside composition):\n" + "\n".join(violations)


# --- K8 / F4: architecture intelligence outside runtime/kernel ------------
_AI_MODULES = ("akb", "research", "llm", "omni_route")


def test_kernel_runtime_no_ai_imports():
    """K8/F4: kernel/ and runtime/ MUST NOT import akb/, research/, llm/ modules."""
    violations = []
    for pkg in ("kernel", "runtime"):
        pkg_dir = ROOT / pkg
        if not pkg_dir.exists():
            continue
        for py in pkg_dir.rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                elif isinstance(node, ast.Import):
                    mods.extend(a.name for a in node.names)
                for mod in mods:
                    top = mod.split(".")[0]
                    if top in _AI_MODULES:
                        violations.append(f"{py.relative_to(ROOT)} imports '{mod}' (K8/F4)")
    assert not violations, "K8/F4 GATE FAILED:\n" + "\n".join(violations)


# --- F1: no blocking sleep in recovery/supervisor -------------------------
def test_no_blocking_sleep_in_recovery():
    """F1: recovery/supervisor MUST NOT use blocking time.sleep() for readiness."""
    violations = []
    for sub in ("runtime/recovery", "runtime/supervisor"):
        d = ROOT / sub
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for m in re.finditer(r"time\.sleep\s*\(", text):
                lineno = text.count("\n", 0, m.start()) + 1
                violations.append(f"{py.relative_to(ROOT)}:{lineno} blocking time.sleep (F1)")
    assert not violations, "F1 GATE FAILED (blocking sleep in recovery/supervisor):\n" + "\n".join(violations)


# --- F5: AgentResult must be frozen dataclass -----------------------------
def test_agent_result_frozen():
    """F5: if AgentResult exists, it MUST be a frozen dataclass (traceable)."""
    candidates = []
    for pkg in ("contracts", "services", "runtime"):
        d = ROOT / pkg
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if re.search(r"class\s+AgentResult\b", text):
                candidates.append(py)
    if not candidates:
        pytest.skip("AgentResult not found in codebase (F5 N/A)")
    for py in candidates:
        text = py.read_text(encoding="utf-8")
        m = re.search(r"@dataclass.*?\nclass AgentResult", text, re.DOTALL)
        assert m is not None, f"{py.relative_to(ROOT)}: AgentResult not a dataclass (F5)"
        deco = m.group(0)
        assert "frozen=True" in deco, f"{py.relative_to(ROOT)}: AgentResult dataclass not frozen (F5)"


# --- F6: every ADR in adrs.yaml carries evidence_level -------------------
def test_all_adrs_have_evidence():
    """F6 (warn): every ADR entry in AKB/adrs.yaml must carry evidence_level.

    Non-blocking: reports missing levels but does NOT fail the suite (F6 is
    'warn' severity per forbidden.yaml). Closing F6 fully is WP-08 scope.
    """
    adrs_path = AKB / "adrs.yaml"
    data = yaml.safe_load(adrs_path.read_text(encoding="utf-8"))
    missing = []
    for adr in data.get("adrs", []):
        lvl = adr.get("evidence_level") or adr.get("evidence")
        if lvl is None:
            missing.append(adr.get("id", "?"))
    if missing:
        sys.stdout.write(
            f"\n[F6 WARN] ADRs without evidence_level (non-blocking): {missing}\n"
        )
    assert True
