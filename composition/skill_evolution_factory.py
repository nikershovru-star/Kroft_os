"""Skill Evolver composition (ТЗ-EVOLUTION-01, ADR-092, Флаг C).

Standalone wiring (composition root may import services + adapters, gate rule: composition ->
everything). SkillEvolver itself (services/skill_evolution.py) imports only contracts; here we
supply the concrete SubprocessSandbox + InMemoryProceduralMemory. NOT wired into build_kernel
(Флаг C) — the evolver is opt-in via this factory.
"""

from __future__ import annotations

from typing import Optional

from adapters.subprocess_sandbox import SubprocessSandbox
from contracts.i_execution_sandbox import IExecutionSandbox
from contracts.i_memory import IProceduralMemory
from services.memory_platform import InMemoryProceduralMemory
from services.skill_evolution import SkillEvolver, build_skill_evolver


def build_default_skill_evolver(min_uses: int = 5, success_threshold: float = 0.8,
                                timeout_sec: float = 5.0) -> SkillEvolver:
    """Build a SkillEvolver over concrete SubprocessSandbox + InMemoryProceduralMemory (Флаг C)."""
    sandbox: IExecutionSandbox = SubprocessSandbox()
    memory: IProceduralMemory = InMemoryProceduralMemory()
    return build_skill_evolver(
        sandbox=sandbox, memory=memory, min_uses=min_uses,
        success_threshold=success_threshold, timeout_sec=timeout_sec,
    )
