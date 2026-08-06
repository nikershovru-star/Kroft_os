"""DelegationService — delegation-DAG с cycle detection + max depth (Phase C, Wave C1).

K1/K6: services импортирует только contracts + stdlib. НЕ трогает ядро/оркестратор.

DAG: parent_goal_id -> child_goal_id. Хранит edges + depth. Перед accept проверяет:
  - cycle: child не должен быть транзитивным предком parent (is_ancestor).
  - max_depth: depth(child) <= max_depth.
Speaker selection = executor_resolver(capability) (capability-index O(1), не перебор).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from contracts.i_delegation import (
    DelegationDecision,
    IDelegationService,
)
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome


class DelegationService(IDelegationService):
    """In-memory delegation-DAG с охраной от циклов и глубины."""

    def __init__(self, max_depth: int = 8) -> None:
        self._max_depth = max_depth
        self._parents: Dict[str, Optional[str]] = {}  # child -> parent (None=root)
        self._children: Dict[str, List[str]] = {}
        self._depth: Dict[str, int] = {}

    def delegate(
        self,
        parent_goal_id: str,
        child_goal: OrchestrationGoal,
        executor_resolver,
    ) -> DelegationDecision:
        child_id = child_goal.goal_id
        # cycle detection: child не должен быть предком parent
        if self.is_ancestor(child_id, parent_goal_id):
            return DelegationDecision(
                child_goal_id=child_id,
                capability=child_goal.capability,
                executor_id="",
                depth=0,
                accepted=False,
                reason=f"delegation cycle: {child_id} is ancestor of {parent_goal_id}",
            )
        parent_depth = self._depth.get(parent_goal_id, 0)
        child_depth = parent_depth + 1
        if child_depth > self._max_depth:
            return DelegationDecision(
                child_goal_id=child_id,
                capability=child_goal.capability,
                executor_id="",
                depth=child_depth,
                accepted=False,
                reason=f"max_depth exceeded: {child_depth} > {self._max_depth}",
            )
        # capability-index O(1) selection
        executor_id = executor_resolver(child_goal.capability) if executor_resolver else None
        if not executor_id:
            return DelegationDecision(
                child_goal_id=child_id,
                capability=child_goal.capability,
                executor_id="",
                depth=child_depth,
                accepted=False,
                reason=f"no executor for capability '{child_goal.capability}'",
            )
        # commit edge
        self._parents[child_id] = parent_goal_id
        self._children.setdefault(parent_goal_id, []).append(child_id)
        self._depth[child_id] = child_depth
        return DelegationDecision(
            child_goal_id=child_id,
            capability=child_goal.capability,
            executor_id=executor_id,
            depth=child_depth,
            accepted=True,
            reason="ok",
        )

    def record_outcome(self, child_goal_id: str, outcome: TaskOutcome) -> None:
        # исход логируется для trust evolution у caller-а; здесь DAG уже зафиксирован
        pass

    def is_ancestor(self, ancestor_goal_id: str, goal_id: str) -> bool:
        """goal_id — транзитивный потомок ancestor_goal_id?

        Исключает саму вершину goal_id (cycle detection только по РОДИТЕЛЯМ, иначе
        delegate(root->root) ложно детектит цикл сам-в-себе).
        """
        cur: Optional[str] = self._parents.get(goal_id)  # начинаем с родителя
        seen: Set[str] = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            if cur == ancestor_goal_id:
                return True
            cur = self._parents.get(cur)
        return False

    def depth_of(self, goal_id: str) -> int:
        return self._depth.get(goal_id, 0)
