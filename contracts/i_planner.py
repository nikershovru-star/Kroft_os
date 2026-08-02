"""Autonomous Planner port (ТЗ-PL-01 / ADR-045) — K1-compliant: contracts + stdlib only.

The Planner is the DELIBERATE candidate generator (ADR-054: Reasoning -> Planning ->
Decision). It turns ReasoningSteps into candidate Plans, runs each through the World
Model (lookahead via simulate), and RANKS them by PREDICTED VALUE-AWARE utility
(ТЗ-PL-01 flag 2). The planner only RANKS — the deterministic Decision Engine still
makes the final pick (I-03 / I-09).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from contracts.cognitive_domain import Goal, Plan, ReasoningStep, WorldState
from contracts.i_world_model import IWorldModel


class IPlanner(ABC):
    """Generates + RANKS candidate plans from reasoning steps (ТЗ-PL-01).

    `plan` returns candidate Plans ordered by predicted value-aware utility. The
    ranking is carried in `Plan.confidence` (a frozen dataclass cannot take an extra
    field); the first element is the highest-utility candidate. The planner must NOT
    make the final selection — that stays with the Decision Engine.

    Without a WorldModel the planner falls back to ranking by reasoning-step
    confidence (backward compatible).
    """

    @abstractmethod
    def plan(self, goal: Goal, reasoning_steps: List[ReasoningStep],
             world: WorldState, budget_tokens: int) -> List[Plan]:
        """Return candidate Plans ranked by predicted utility (best first)."""
