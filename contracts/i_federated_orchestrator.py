"""Federated orchestration ports (ТЗ-FED-ORCH-01 client + ТЗ-FED-EXEC-01 server, ADR-075/076).

K5 (commit 0): `INetworkTransport` (NW-01) — broadcast-only (send_event/send_facts/
send_soft_layer + on_*), НЕТ request/response RPC для goal-dispatch. Поэтому клиентский порт
`IRemoteOrchestrator` — НОВЫЙ (one-port-per-boundary: транспорт ≠ оркестрация). `INetworkTransport`
переиспользуется КАК carrier в reference-имплементациях (send_facts/on_facts несут dict-конверты
по correlation-id), НЕ дублируется. `ITrustRegistry` (IDT-01) переиспользуется для trust-gating
(current_trust) и обновления (record_outcome из реального remote-исхода).

ТЗ-FED-EXEC-01 (commit 1): серверная половина — `IRemoteExecutionListener`. НЕ дублирует
`IRemoteOrchestrator` (client); это сервер (one-port-per-boundary: client ≠ server).

K5 (FED-EXEC-01, commit 0): FED-ORCH-01 wire-helpers были ПРИВАТНЫ в kernel/federated_orchestrator.py.
Централизованы здесь (REQ_MARKER/RESP_MARKER + encode_*/decode_*) как SINGLE SOURCE OF TRUTH —
client и server используют ОДИН формат (НЕ дублируют). Client отрефакторен на их использование
(behaviour-preserving; доказано FED-ORCH-01 тестами).

Trust-gating: dispatch_remote/client шлёт ТОЛЬКО на узлы с current_trust(node) >= threshold
(закрывает Флаг 1 IDT-01: current_trust = LATEST, НЕ trust_score_of = MAX). Реальный remote-outcome
(success/failure) обновляет trust узла -> failure РЕАЛЬНО понижает (закрывает Флаг 2 ORCH-01:
agent-dispatch больше не always-success). Сервер НЕ мутирует remote trust (O1).

K1: contracts + stdlib only. Frozen VO с реальными типами (урок Флага 1 LLM-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from contracts.cognitive_domain import CausalMark
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome

# Wire markers (single source of truth; client + server share them).
REQ_MARKER = "__fed_orch_req__"
RESP_MARKER = "__fed_orch_resp__"


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


# ---------------------------------------------------------------------------
# Wire (de)serialization — SINGLE SOURCE OF TRUTH for client + server (K5).
# ---------------------------------------------------------------------------
def encode_goal_request(req: RemoteGoalRequest) -> dict:
    goal = req.goal
    causal = req.causal.to_dict() if isinstance(req.causal, CausalMark) else None
    return {
        REQ_MARKER: True,
        "request_id": req.request_id,
        "node_id": req.node_id,
        "author_id": req.author_id,
        "causal": causal,
        "goal": {
            "goal_id": goal.goal_id,
            "capability": goal.capability,
            "required_permission": goal.required_permission,
            "payload": goal.payload,
        },
    }


def decode_goal_request(fact: dict) -> RemoteGoalRequest:
    g = fact["goal"]
    return RemoteGoalRequest(
        request_id=fact["request_id"],
        node_id=fact["node_id"],
        author_id=fact["author_id"],
        causal=CausalMark.from_dict(fact.get("causal")),  # round-trip lamport for replay-key
        goal=OrchestrationGoal(
            goal_id=g["goal_id"],
            capability=g["capability"],
            required_permission=g.get("required_permission"),
            payload=g.get("payload"),
        ),
    )


def encode_outcome_response(resp: RemoteOutcomeResponse) -> dict:
    causal = resp.causal.to_dict() if isinstance(resp.causal, CausalMark) else None
    return {
        RESP_MARKER: True,
        "request_id": resp.request_id,
        "node_id": resp.node_id,
        "author_id": resp.author_id,
        "causal": causal,
        "outcome": {"success": resp.outcome.success, "detail": resp.outcome.detail},
    }


def decode_outcome_response(fact: dict) -> RemoteOutcomeResponse:
    o = fact["outcome"]
    return RemoteOutcomeResponse(
        request_id=fact["request_id"],
        node_id=fact["node_id"],
        author_id=fact["author_id"],
        causal=CausalMark.from_dict(fact.get("causal")),  # round-trip lamport for replay-key
        outcome=TaskOutcome(success=o["success"], detail=o["detail"]),
    )


def is_goal_request(fact: Any) -> bool:
    return isinstance(fact, dict) and bool(fact.get(REQ_MARKER))


def is_outcome_response(fact: Any) -> bool:
    return isinstance(fact, dict) and bool(fact.get(RESP_MARKER))


class IRemoteOrchestrator:
    """Dispatch a goal to a remote trusted node and return the REAL outcome (ТЗ-FED-ORCH-01, client).

    The remote node executes locally (its own orchestrator/plugin) and returns a real
    TaskOutcome. Trust is updated from that real outcome by the implementation (success +,
    failure -) via ITrustRegistry.record_outcome.
    """

    def dispatch_remote(self, node_id: str, goal: OrchestrationGoal) -> TaskOutcome:
        raise NotImplementedError


class IRemoteExecutionListener:
    """Server side: execute RemoteGoalRequest locally and return the REAL outcome (ТЗ-FED-EXEC-01).

    Subscribes to incoming goal-requests (carrier: on_facts), filters by node_id (only
    requests addressed to THIS node; ignores others), executes the goal with the local
    orchestrator/plugin, and ships the real RemoteOutcomeResponse back via send_facts.

    K5: НЕ дублирует IRemoteOrchestrator (that is the client). One-port-per-boundary:
    client (dispatch) ≠ server (listen+execute).
    O1: server does NOT mutate remote trust; the CLIENT updates its own trust from the
    received outcome (handled by the client, not here).
    """

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
