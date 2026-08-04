"""Trust-aware orchestration port (ТЗ-ORCH-01, ADR-073).

K5 (commit 0): K5-разведка нашла, что trust-aware ROUTING НЕ существовало. Смежные порты
УЖЕ есть и переиспользуются, НЕ дублируются:
- ``IIdentityRegistry`` / ``ITrustRegistry`` / ``IActionLog`` (ТЗ-IDT-01, contracts/i_identity.py)
  — переиспользуются. ITrustRegistry расширен (record_outcome/current_trust) для эволюции
  trust из исхода; trust_score_of (MAX) НЕ тронут (FSE-01 gating цел).
- ``IPluginRegistry`` (ТЗ-PLUGIN-01, contracts/plugin.py) — переиспользуется (invoke).
- ``IAgentPlatform`` (ТЗ-AGENT-001) — это agent-platform (execute/run/ask), НЕ оркестратор;
  его НЕ дублируем. ReferenceOrchestrator логирует outcome агента (реальное сетевое
  исполнение — future, NW-01), не вызывает IAgentPlatform.execute.

ORCH-01 маршрутизирует goal к лучшему исполнителю (agent ИЛИ plugin) по
specialization-match * trust_level, исключает permission-violating / low-trust, исполняет,
логирует в IActionLog и обновляет trust из исхода (success +, failure -) -> петля эволюции.

O1: orchestrator НЕ мутирует HARD/FSM; trust-обновления — SOFT (через ITrustRegistry).
I-09: scoring детерминирован, тай-брейкер по id. K1: contracts + stdlib only.
Frozen VO с реальными типами (урок Флага 1 LLM-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass(frozen=True)
class OrchestrationGoal:
    """A unit of work routed by the orchestrator (ТЗ-ORCH-01)."""
    goal_id: str
    capability: str                       # required capability to match candidates
    required_permission: Optional[str] = None  # if set, candidate must hold it
    payload: Any = None                   # passed to the chosen executor (plugin args)


@dataclass(frozen=True)
class RoutingDecision:
    """Deterministic routing result (ТЗ-ORCH-01)."""
    chosen_id: str
    kind: str                             # 'agent' | 'plugin'
    rationale: str
    score: float


@dataclass(frozen=True)
class TaskOutcome:
    """Result of a dispatched task (ТЗ-ORCH-01)."""
    success: bool
    detail: str


class IOrchestrator:
    """Trust-aware orchestrator: route -> best executor; dispatch -> log + trust update."""

    def route(self, goal: OrchestrationGoal) -> Optional[RoutingDecision]:
        raise NotImplementedError

    def dispatch(self, goal: OrchestrationGoal) -> TaskOutcome:
        raise NotImplementedError
