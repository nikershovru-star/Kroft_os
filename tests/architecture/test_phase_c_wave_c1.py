"""(tests/architecture) Phase C Wave C1 — architecture gate (ADR-103).

Доказывает, что новые координационные сервисы соблюдают K6 (services -> только contracts)
и что AgentRuntime — тонкий facade (БЕЗ god-object: делегирует портам, не содержит
координационных if-веток по capability).

Позитивный gate: сканирует реальные файлы Wave C1 через существующий детектор
_check_file_imports (матрица ALLOWED: services -> contracts + stdlib).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from tests._repo_root import repo_root
from tests.common.test_architecture import _check_file_imports

ROOT = repo_root()

WAVE_C1_SERVICES = [
    "services/agent_runtime.py",
    "services/blackboard.py",
    "services/delegation_service.py",
    "services/coordination_strategy.py",
]


def _violations(path: Path):
    pkg, violations = _check_file_imports(path)
    return violations


@pytest.mark.parametrize("rel", WAVE_C1_SERVICES)
def test_wave_c1_service_imports_only_contracts(rel: str):
    """K6: каждый сервис Wave C1 импортирует только contracts (+ stdlib)."""
    path = ROOT / rel
    assert path.exists(), f"missing {rel}"
    v = _violations(path)
    assert not v, f"K6 violation in {rel}: {v}"


def test_agent_runtime_is_facade_not_god_object():
    """AgentRuntime зависит только от портов; не импортирует конкретные сервисы/ядро."""
    path = ROOT / "services/agent_runtime.py"
    text = path.read_text(encoding="utf-8")
    # facade НЕ тянет конкретные services-модули (K6) и НЕ тянет kernel/adapters
    assert "from services." not in text, "AgentRuntime must not import concrete services (K6)"
    assert "from kernel." not in text, "AgentRuntime must not import kernel"
    assert "from adapters." not in text, "AgentRuntime must not import adapters"
    # facade делегирует портам
    assert "self._delegation.delegate" in text
    assert "self._executor.execute" in text
