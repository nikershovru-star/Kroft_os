"""Federated orchestration port (ТЗ-FED-ORCH-01, ADR-075).

K5 (commit 0): `INetworkTransport` (NW-01) — broadcast-only (send_event/send_facts/
send_soft_layer + on_*), НЕТ request/response RPC для goal-dispatch. Поэтому этот порт —
НОВЫЙ (one-port-per-boundary: транспорт ≠ оркестрация). `INetworkTransport` переиспользуется
КАК carrier в reference-имплементации (send_facts/on_facts несут dict-конверты по
correlation-id), НЕ дублируется. `ITrustRegistry` (IDT-01) переиспользуется для trust-gating
(current_trust) и обновления (record_outcome из реального remote-исхода).

Trust-gating: dispatch_remote выполняется ТОЛЬКО на узлы с current_trust(node) >= threshold
(закрывает Флаг 1 IDT-01: current_trust = LATEST, НЕ trust_score_of = MAX). Реальный
remote-outcome (success/failure) обновляет trust узла -> failure РЕАЛЬНО понижает (закрывает
Флаг 2 ORCH-01: agent-dispatch больше не always-success).

K1: contracts + stdlib only. Frozen VO с реальными типами (урок Флага 1 LLM-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from contracts.cognitive_domain import CausalMark
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome


@dataclass(frozen=True)
class RemoteGoalRequest:
    """Wire request: dispatch `goal` on a remote trusted node (ТЗ-FED-ORCH-01)."""

    request_id: str
    node_id: str
    goal: OrchestrationGoal
    author_id: str
    causal: Optional[CausalMark] = None


@dataclass(frozen=True)
class RemoteOutcomeResponse:
    """Wire response: real TaskOutcome from the remote node (ТЗ-FED-ORCH-01)."""

    request_id: str
    node_id: str
    outcome: TaskOutcome
    author_id: str
    causal: Optional[CausalMark] = None


class IRemoteOrchestrator:
    """Dispatch a goal to a remote trusted node and return the REAL outcome (ТЗ-FED-ORCH-01).

    The remote node executes locally (its own orchestrator/plugin) and returns a real
    TaskOutcome. Trust is updated from that real outcome by the implementation (success +,
    failure -) via ITrustRegistry.record_outcome.
    """

    def dispatch_remote(self, node_id: str, goal: OrchestrationGoal) -> TaskOutcome:
        raise NotImplementedError
