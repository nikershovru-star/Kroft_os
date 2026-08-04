"""Reference remote execution listener (ТЗ-FED-EXEC-01 server, ADR-076) — deterministic, LLM-free.

K5 (commit 0): НЕ дублирует INetworkTransport (NW-01) — переиспользует КАК carrier через
send_facts/on_facts. НЕ дублирует IRemoteOrchestrator (client) — это СЕРВЕР (one-port-per-boundary).
НЕ дублирует ReferenceOrchestrator (ORCH-01) — переиспользует ЕГО для локального исполнения
(реальный outcome из локального plugin/agent). Wire-формат переиспользуется из
contracts/i_federated_orchestrator.py (encode_outcome_response/is_goal_request/decode_goal_request)
— НЕ дублирует client.

Роль сервера: подписка on_facts, фильтр по node_id (только запросы НА ЭТОТ узел; чужие игнорируются),
локальное исполнение goal через IOrchestrator.dispatch (реальный TaskOutcome), отправка
RemoteOutcomeResponse через send_facts. Детерминизм (I-09): correlation по request_id.

O1: сервер НЕ мутирует trust (ни свой, ни remote) — trust ЭВОЛЮЦИОНИРУЕТ на КЛИЕНТЕ из полученного
исхода (IRemoteOrchestrator.dispatch_remote -> record_outcome). Сервер мутирует только ЛОКАЛЬНЫЙ
исполнитель (plugin/agent), что в рамках своего узла. HARD/FSM не трогаются.

Флаг C: build_remote_execution_listener — standalone фабрика, НЕ в build_kernel.
"""

from __future__ import annotations

from typing import List

from contracts.i_federated_orchestrator import (
    is_goal_request,
    decode_goal_request,
    encode_outcome_response,
    RemoteOutcomeResponse,
)
from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import IOrchestrator


class RemoteExecutionListener:
    """Server side: execute incoming RemoteGoalRequest locally, return real outcome.

    Wires a node as a SERVICE node (Tachikoma-style autonomous service agent): it listens
    for goal-requests addressed to its `node_id`, runs them through its own local
    orchestrator/plugin, and ships the REAL TaskOutcome back to the requester.

    K5: implements IRemoteExecutionListener contract; does NOT duplicate the client port.
    """

    def __init__(self, transport: INetworkTransport, orchestrator: IOrchestrator, node_id: str) -> None:
        self._t = transport
        self._orch = orchestrator
        self._node_id = node_id
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._t.on_facts(self._on_facts)
        self._running = True

    def stop(self) -> None:
        self._running = False

    def _on_facts(self, facts: List[dict], sender_node_id: str) -> None:
        if not self._running:
            return
        for fact in facts:
            if not is_goal_request(fact):
                continue
            req = decode_goal_request(fact)
            # Filter: only requests addressed to THIS node (ignore others, K5/ТЗ gotcha).
            if req.node_id != self._node_id:
                continue
            # Local real execution (reuses ReferenceOrchestrator.dispatch -> real outcome).
            outcome = self._orch.dispatch(req.goal)
            resp = RemoteOutcomeResponse(
                request_id=req.request_id,
                node_id=self._node_id,
                outcome=outcome,
                author_id=self._node_id,
                causal=None,
            )
            # Carrier: ship the response back via NW-01 send_facts (broadcast; client correlates).
            self._t.send_facts([encode_outcome_response(resp)], self._node_id)


def build_remote_execution_listener(
    transport: INetworkTransport, orchestrator: IOrchestrator, node_id: str
) -> RemoteExecutionListener:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return RemoteExecutionListener(transport, orchestrator, node_id)
