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

from typing import List, Tuple

from contracts.i_federated_orchestrator import (
    is_goal_request,
    decode_goal_request,
    encode_outcome_response,
    RemoteOutcomeResponse,
)
from contracts.i_identity import ITrustRegistry
from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import IOrchestrator
from kernel.federated_orchestrator import build_remote_orchestrator


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


def build_federated_node(
    transport: INetworkTransport,
    orchestrator: IOrchestrator,
    trust: ITrustRegistry,
    node_id: str,
    trust_threshold: float = 0.2,
    trust_delta: float = 0.1,
    remote_nodes: Tuple[str, ...] = (),
) -> "FederatedNode":
    """Integration glue (ТЗ-FED-EXEC-01 commit 3, Флаг C): a SERVICE node = client + server.

    A node is BOTH a client (can dispatch goals to trusted remote nodes) AND a server
    (executes goals addressed to it locally). It shares ONE local orchestrator, ONE trust
    registry, and ONE transport between the client (IRemoteOrchestrator) and the server
    (IRemoteExecutionListener) — so dispatch and execution are coherent on the same substrate.

    K5: reuses build_remote_orchestrator (client) + build_remote_execution_listener (server);
    does NOT duplicate them. Standalone factory — НЕ in build_kernel.
    O1: server does not mutate remote trust; the client updates local trust from real outcomes.

    REAL-TCP readiness (ТЗ-FED-TCP-01): this factory is transport-agnostic (Флаг 1 fix,
    commit 321fc21) and accepts the real `NetworkTransport` (adapters/network_transport.py, NW-01
    localhost TCP) as `transport` — no new port required. The caller (test/composition-root, NOT
    kernel/adapters cross-import) wires `NetworkTransport(node_id, port).connect(node_id, [peer])`
    then passes it here; the single delegated on_facts handler fans out to client+server regardless
    of whether the concrete transport fan-outs or single-slots. НЕ дублирует
    INetworkTransport/IRemoteOrchestrator.

    TRANSPORT-AGNOSTIC fan-out (Флаг 1 fix, 2026-08-04): `INetworkTransport.on_facts` does NOT
    guarantee fan-out — a real NW-01 TCP transport overwrites its single subscriber slot, so
    registering both the client and the server directly would lose one handler. Instead we
    register ONE delegating handler that fans out to the client and server internally. This is
    transport-agnostic: works for both SyncTransport (test) and real TCP NW-01.
    """
    client = build_remote_orchestrator(
        transport, trust, trust_threshold=trust_threshold,
        trust_delta=trust_delta, local_node_id=node_id,
    )
    server = build_remote_execution_listener(transport, orchestrator, node_id)

    # Internal fan-out delegate: a single on_facts subscription that forwards to both
    # the client (response correlation) and the server (request handling).
    def _delegate(facts: List[dict], sender_node_id: str) -> None:
        client._on_facts(facts, sender_node_id)
        server._on_facts(facts, sender_node_id)

    # Override the per-component subscriptions with a single delegating handler on the
    # transport. Both client._on_facts and server._on_facts are still exercised; only the
    # transport slot is unified (transport-agnostic, no reliance on on_facts fan-out).
    transport.on_facts(_delegate)

    return FederatedNode(client, server, node_id, _delegate)



class FederatedNode:
    """A node that is both a federated client and a remote-execution server (ТЗ-FED-EXEC-01)."""

    def __init__(self, client, server, node_id: str, delegate=None) -> None:
        self.client = client
        self.server = server
        self.node_id = node_id
        self._delegate = delegate

    def start(self) -> None:
        # The fan-out delegate is ALREADY subscribed in build_federated_node (transport-agnostic
        # fix for Флаг 1). Do NOT re-subscribe per-component here (would overwrite the slot on
        # real NW-01 TCP). Just mark the server running.
        self.server._running = True

    def stop(self) -> None:
        self.server._running = False

    def dispatch_remote(self, node_id: str, goal) -> "TaskOutcome":
        """Client path: dispatch a goal to a trusted remote node (real outcome + trust update)."""
        return self.client.dispatch_remote(node_id, goal)

