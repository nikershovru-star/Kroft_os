"""composition/runtime_factory.py — Runtime layer assembly (Phase B.1).

Точка создания runtime-компонентов (CapabilityRegistry и т.д.). Расширяема для
будущего: Supervisor, RecoveryState, HotReload — добавляются сюда, ядро не меняется.
"""
from __future__ import annotations

from runtime import CapabilityRegistry


def build_capability_registry() -> CapabilityRegistry:
    """Capability registry — чистый runtime-объект, без infrastructure-зависимостей."""
    return CapabilityRegistry()
