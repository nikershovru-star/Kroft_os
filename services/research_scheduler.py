"""L8 Autonomous Research Scheduler (ADR-0XX).

K6-compliant: services/ imports ONLY contracts.* + stdlib. Drives an
``IAgentPlatform`` (e.g. ``ResearchAgent``) in an autonomous loop that
self-sets research goals and accrues findings for KB-Update.

Deterministic (I-09): ``run_for(n)`` performs exactly ``n`` in-process ticks
with NO real sleep — safe to call from tests and from ``run_evolution.py``.
Graceful degradation (O1): with an LLM-free agent the loop still produces
findings (the agent returns graph hits verbatim).
"""
from __future__ import annotations

from typing import List, Optional

from contracts.i_agent_platform import (
    IAgentPlatform,
    ResearchFinding,
)


class AutonomousResearchScheduler:
    """L8: autonomous research loop with self-set goals (ADR-0XX).

    Goals are drawn from a seed pool; after each successful research the scheduler
    DERIVES a new goal from the result's source hits (self-set goals — L7/L8
    autonomy), up to ``max_generated_goals`` derived goals, so the loop can run
    autonomously beyond the initial seed.
    """

    def __init__(self, agent: IAgentPlatform, goal_seed: Optional[List[str]] = None,
                 max_generated_goals: int = 0) -> None:
        if agent is None:
            raise TypeError("AutonomousResearchScheduler requires an IAgentPlatform instance")
        self._agent = agent
        self._seed = list(goal_seed or [])
        self._max_generated = max(0, int(max_generated_goals))
        self._generated = 0
        self._tick_no = 0
        self._history: List[ResearchFinding] = []

    # --- IResearchScheduler ------------------------------------------------
    def tick(self) -> Optional[ResearchFinding]:
        goal = self._next_goal()
        if goal is None:
            return None
        self._tick_no += 1
        result = self._agent.run(goal)
        finding = ResearchFinding(
            goal=goal,
            answer=(result.tool_results[-1] if result.tool_results else result.status),
            success=result.is_success,
            source_hits=tuple(result.knowledge_hits),
            tick=self._tick_no,
        )
        self._history.append(finding)
        if finding.success and self._generated < self._max_generated:
            self._derive_goal(finding)
        return finding

    def run_for(self, n: int) -> List[ResearchFinding]:
        collected: List[ResearchFinding] = []
        for _ in range(max(0, int(n))):
            f = self.tick()
            if f is None:
                break
            collected.append(f)
        return collected

    def findings(self) -> List[ResearchFinding]:
        return list(self._history)

    # --- internals ---------------------------------------------------------
    def _next_goal(self) -> Optional[str]:
        if self._seed:
            return self._seed.pop(0)
        return None

    def _derive_goal(self, finding: ResearchFinding) -> None:
        """Self-set a new goal derived from a successful finding's sources."""
        if finding.source_hits:
            derived = f"follow-up: deeper analysis of {finding.source_hits[0]}"
        else:
            derived = f"expand research on '{finding.goal}'"
        self._seed.append(derived)
        self._generated += 1
