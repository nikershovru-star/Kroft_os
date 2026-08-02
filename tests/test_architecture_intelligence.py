"""Tests for WP-12 Architecture Intelligence (ADR-042).

Targets >=10 tests. Verifies L5 Simulator, L6 Tech Debt Engine, L7 Evolution
Engine reuse AKB + telemetry. Negative proof-of-fire (K1/K8).
"""
import tempfile
from pathlib import Path

from contracts.i_architecture_intelligence import (
    IChangeSimulator, ITechDebtAuditor, IEvolutionPlanner,
)
from contracts.i_telemetry import ITelemetrySink
from services.architecture_intelligence import (
    ArchitectureSimulator, TechDebtEngine, EvolutionEngine,
)
from adapters.in_memory_telemetry import InMemoryTelemetrySink
from contracts.i_execution_sandbox import IExecutionSandbox, ExecutionResult


class _FakeSandbox(IExecutionSandbox):
    def __init__(self, rc=0): self._rc = rc
    def execute(self, command, env=None, timeout_sec=None, cwd=None, label=""):
        return ExecutionResult(returncode=self._rc, stdout="", stderr="", handle="h", duration_ms=1.0)
    def kill(self, handle): return False
    def health(self): return True


def _write_akb(base: Path):
    (base / "adrs.yaml").write_text(
        "adrs:\n"
        "- id: ADR-001\n  status: accepted\n"
        "- id: ADR-099\n  status: proposed\n", encoding="utf-8")
    return str(base)


def test_l5_simulator_detects_forbidden_import():
    d = Path(tempfile.mkdtemp()) / "kernel"
    d.mkdir()
    bad = d / "x.py"
    bad.write_text("import services.something\n", encoding="utf-8")
    sim = ArchitectureSimulator(sandbox=_FakeSandbox())
    res = sim.simulate_imports([str(bad)])
    assert res.ok is False
    assert any("forbidden import 'services'" in v for v in res.predicted_violations)


def test_l5_simulator_clean_file_ok():
    d = Path(tempfile.mkdtemp()) / "kernel"
    d.mkdir()
    good = d / "y.py"
    good.write_text("from contracts import Foo\nimport os\n", encoding="utf-8")
    sim = ArchitectureSimulator(sandbox=_FakeSandbox())
    res = sim.simulate_imports([str(good)])
    assert res.ok is True
    assert res.predicted_violations == []


def test_l5_dry_run_command():
    sim = ArchitectureSimulator(sandbox=_FakeSandbox(rc=0))
    res = sim.dry_run_command(["echo", "x"])
    assert res.ok is True
    sim_bad = ArchitectureSimulator(sandbox=_FakeSandbox(rc=1))
    res_bad = sim_bad.dry_run_command(["false"])
    assert res_bad.ok is False


def test_l6_audit_stale_adr():
    akb = _write_akb(Path(tempfile.mkdtemp()))
    eng = TechDebtEngine(akb_path=akb, telemetry=None)
    report = eng.audit()
    assert report.score > 0.0
    assert any(i.area == "adr-lifecycle" for i in report.items)
    assert report.high_count == 0  # stale ADR = low severity


def test_l6_audit_drift_metric_high():
    akb = _write_akb(Path(tempfile.mkdtemp()))
    tel = InMemoryTelemetrySink(capacity=100)
    for _ in range(3):
        tel.record("drift.score", 0.9)
    eng = TechDebtEngine(akb_path=akb, telemetry=tel)
    report = eng.audit()
    assert any(i.area == "drift" and i.severity == "high" for i in report.items)


def test_l7_plan_from_drift():
    akb = _write_akb(Path(tempfile.mkdtemp()))
    tel = InMemoryTelemetrySink(capacity=100)
    tel.record("drift.score", 0.9)
    eng = EvolutionEngine(akb_path=akb, telemetry=tel)
    road = eng.plan()
    assert any("boundary" in i.title.lower() or "k1" in i.title.lower() or "k8" in i.title.lower()
               for i in road.items)
    assert any(i.priority == "high" for i in road.items)


def test_l7_plan_from_circuit_trend():
    akb = _write_akb(Path(tempfile.mkdtemp()))
    tel = InMemoryTelemetrySink(capacity=100)
    for _ in range(6):
        tel.record("circuit.trip", 1.0)
    eng = EvolutionEngine(akb_path=akb, telemetry=tel)
    road = eng.plan()
    assert any("recovery" in i.title.lower() for i in road.items)


def test_l7_plan_combines_debt():
    akb = _write_akb(Path(tempfile.mkdtemp()))
    tel = InMemoryTelemetrySink(capacity=100)
    tel.record("drift.score", 0.9)
    debt = TechDebtEngine(akb_path=akb, telemetry=tel)
    eng = EvolutionEngine(akb_path=akb, telemetry=tel, debt_engine=debt)
    road = eng.plan()
    assert len(road.items) >= 2  # drift + debt both contribute


def test_ports_respected():
    assert issubclass(ArchitectureSimulator, IChangeSimulator)
    assert issubclass(TechDebtEngine, ITechDebtAuditor)
    assert issubclass(EvolutionEngine, IEvolutionPlanner)


def test_negative_k1_port_clean():
    import inspect
    src = inspect.getsource(IChangeSimulator)
    assert "import services" not in src and "from services" not in src
    assert "import runtime" not in src and "from runtime" not in src


def test_negative_k8_service_clean():
    import inspect
    src = inspect.getsource(ArchitectureSimulator) + inspect.getsource(TechDebtEngine) + inspect.getsource(EvolutionEngine)
    assert "import kernel" not in src and "from kernel" not in src
    assert "import runtime" not in src and "from runtime" not in src
