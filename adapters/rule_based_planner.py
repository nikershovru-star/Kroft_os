"""RuleBasedPlanner — keyword-driven IPlanner (Wave 10, ADR-013 Phase C).

Deliberately NOT a neural planner. v0.1 matches keywords in the goal and emits a
fixed step template; the LLM planner is Wave 11 and will be the SECOND
implementation of `IPlanner` (LAW 6).

Determinism is a hard requirement, not a nicety: the Wave 10 DoD says a workflow
must be reproducible, so the same goal MUST always yield the same plan. That
rules out dict iteration order and set ordering — templates live in an ordered
tuple and the first match wins.
"""
from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

from contracts.i_policy import PolicyContext
from contracts.i_workflow import IPlanner, Step

# (template name, trigger keywords, step tasks)
# Ordered: the FIRST matching template wins, so overlapping goals resolve
# predictably ("compare and summarize" -> compare).
Template = Tuple[str, Tuple[str, ...], Tuple[str, ...]]

DEFAULT_TEMPLATES: Tuple[Template, ...] = (
    (
        "compare",
        ("compare", "versus", " vs ", "difference", "сравни", "различия"),
        ("retrieve_A", "retrieve_B", "compare", "validate"),
    ),
    (
        "summarize",
        ("summarize", "summary", "tldr", "суммируй", "кратко", "резюме"),
        ("extract_entities", "summarize", "validate"),
    ),
    (
        "explain",
        ("explain", "why", "how does", "объясни", "почему"),
        ("retrieve_context", "explain", "fact_check"),
    ),
)

DEFAULT_PLAN: Tuple[str, ...] = ("analyze", "execute", "validate")


class RuleBasedPlanner(IPlanner):
    """Keyword matching over an ordered template table.

    Args:
        templates: optional override, same shape as DEFAULT_TEMPLATES.
    """

    def __init__(self, templates: Sequence[Template] = DEFAULT_TEMPLATES) -> None:
        self._templates = tuple(templates)

    # --- IPlanner ----------------------------------------------------------
    def plan(self, goal: str, context: PolicyContext = None) -> List[Step]:
        tasks = self._match(goal)
        return [
            Step(id=f"s{n}_{task}", task=self._render(task, goal))
            for n, task in enumerate(tasks, start=1)
        ]

    def template_for(self, goal: str) -> str:
        """Name of the template that would be used (introspection/tests)."""
        needle = self._normalise(goal)
        for name, keywords, _ in self._templates:
            if any(k.strip() in needle for k in keywords):
                return name
        return "default"

    # --- internals ---------------------------------------------------------
    def _match(self, goal: str) -> Tuple[str, ...]:
        needle = self._normalise(goal)
        for _name, keywords, tasks in self._templates:
            if any(k.strip() in needle for k in keywords):
                return tasks
        return DEFAULT_PLAN

    @staticmethod
    def _normalise(goal: str) -> str:
        """Lowercase and collapse whitespace so ' vs ' matches reliably."""
        return re.sub(r"\s+", " ", f" {(goal or '').lower()} ")

    @staticmethod
    def _render(task: str, goal: str) -> str:
        """Human-readable step task carrying the original goal."""
        return f"{task}: {goal}"
