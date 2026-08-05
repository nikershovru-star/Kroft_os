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
    RoutingHeader,
)
from contracts.i_identity import ITrustRegistry
from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import IOrchestrator
from contracts.i_signature import (
    ISignatureProvider, attach_signature, check_signature, verify_envelope,
)
from contracts.cognitive_domain import NodeLamportClock
from kernel.crypto import ReplayGuard
from kernel.federated_orchestrator import build_remote_orchestrator
from kernel.orchestrator import build_orchestrator


class RemoteExecutionListener:
    """Server side: execute incoming RemoteGoalRequest locally, return real outcome.

    Wires a node as a SERVICE node (Tachikoma-style autonomous service agent): it listens
    for goal-requests addressed to its `node_id`, runs them through its own local
    orchestrator/plugin, and ships the REAL TaskOutcome back to the requester.

    K5: implements IRemoteExecutionListener contract; does NOT duplicate the client port.
    """

    def __init__(
        self,
        transport: INetworkTransport,
        orchestrator: IOrchestrator,
        node_id: str,
        signature_provider: Optional[ISignatureProvider] = None,
        replay_guard: Optional[ReplayGuard] = None,
    ) -> None:
        self._t = transport
        self._orch = orchestrator
        self._node_id = node_id
        self._sig = signature_provider  # ТЗ-CRYPTO-01: verify incoming, sign outgoing (None = legacy)
        # ТЗ-CRYPTO-HARDEN-01: per-origin replay window (shared with the client on this node).
        self._replay = replay_guard if replay_guard is not None else ReplayGuard()
        self._clock = NodeLamportClock(node_id)  # monotonic seq source for outgoing responses
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
            # ТЗ-CRYPTO-01 + HARDEN-01: verify origin/integrity/version/size AND replay BEFORE
            # executing. A forged/tampered/wrong-key/unsigned/version-mismatch/oversized/replayed
            # request is dropped — we never execute or reply to an unauthenticated dispatch.
            if not verify_envelope(fact, self._sig, replay_guard=self._replay):
                continue
            req = decode_goal_request(fact)
            # Filter: only requests addressed to THIS node (ignore others, K5/ТЗ gotcha).
            if req.node_id != self._node_id:
                continue
            # Local real execution (reuses ReferenceOrchestrator.dispatch -> real outcome).
            outcome = self._orch.dispatch(req.goal)
            causal = self._clock.tick()  # ТЗ-CRYPTO-HARDEN-01: monotonic seq on the response
            # ТЗ-NET-ROUTE-01: if the request arrived via multi-hop, route the response BACK to the
            # ORIGINAL requester (req.author_id) through the same routing table. The ORIGINAL
            # signature/auth is preserved end-to-end; ttl decremented so the return path is bounded.
            resp_route = None
            if req.route is not None:
                resp_route = RoutingHeader(target=req.author_id, ttl=max(1, req.route.ttl - 1))
            resp = RemoteOutcomeResponse(
                request_id=req.request_id,
                node_id=self._node_id,
                outcome=outcome,
                author_id=self._node_id,
                causal=causal,
                route=resp_route,
            )
            # Carrier: ship the response back via NW-01 send_facts (broadcast; client correlates).
            # ТЗ-CRYPTO-01: sign the outgoing response (attaches "signature" when provider set).
            self._t.send_facts([attach_signature(encode_outcome_response(resp), self._sig)], self._node_id)


def build_remote_execution_listener(
    transport: INetworkTransport, orchestrator: IOrchestrator, node_id: str,
    signature_provider: Optional[ISignatureProvider] = None,
    replay_guard: Optional[ReplayGuard] = None,
) -> RemoteExecutionListener:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return RemoteExecutionListener(
        transport, orchestrator, node_id,
        signature_provider=signature_provider, replay_guard=replay_guard,
    )


def build_federated_node(
    transport: INetworkTransport,
    orchestrator: Optional[IOrchestrator],
    trust: ITrustRegistry,
    node_id: str,
    trust_threshold: float = 0.2,
    trust_delta: float = 0.1,
    remote_nodes: Tuple[str, ...] = (),
    *,
    agent_executor: Optional["IAgentExecutor"] = None,
    identity_registry=None,
    plugin_registry=None,
    action_log=None,
    signature_provider: Optional["ISignatureProvider"] = None,
    replay_guard: Optional["ReplayGuard"] = None,
    routing_table: Optional["IRoutingTable"] = None,
    direct_peers: Optional[List[str]] = None,
) -> "FederatedNode":
    """Integration glue (ТЗ-FED-EXEC-01 commit 3, Флаг C): a SERVICE node = client + server.

    A node is BOTH a client (can dispatch goals to trusted remote nodes) AND a server
    (executes goals addressed to it locally). It shares ONE local orchestrator, ONE trust
    registry, and ONE transport between the client (IRemoteOrchestrator) and the server
    (IRemoteExecutionListener) — so dispatch and execution are coherent on the same substrate.

    K5 (commit 0, ТЗ-NET-AGENT-EXEC-01): НЕ дублирует порты. Разведка показала:
    - `RemoteExecutionListener._on_facts` исполняет `self._orch.dispatch(req.goal)` —
      ЛОКАЛЬНЫМ orchestrator'ом СЕРВЕРА. Значит УДАЛЁННЫЙ узел исполняет agent-routed цели
      РЕАЛЬНЫМ агентом, ЕСЛИ его orchestrator собран с `agent_executor`
      (ТЗ-AGENT-EXEC-01, уже поддерживает: ReferenceOrchestrator.dispatch строки 138-143).
    - `IAgentExecutor` / `IRemoteOrchestrator` / `IRemoteExecutionListener` УЖЕ существуют
      (ADR-080 / 075 / 076). НОВЫЙ порт НЕ нужен (one-port-per-boundary сохранён).
    - Точка интеграции: composition-root (`tests/fed_tcp_helpers.py`) строит orchestrator —
      достаточно передать `agent_executor` туда. `build_federated_node` принимает ГОТОВЫЙ
      orchestrator (transport-agnostic glue). См. ТЗ-NET-AGENT-EXEC-01 commit 1/2: тонкое
      расширение `build_federated_node` опц. `agent_executor` (Флаг C, reuse, без дублирования).

    ТЗ-NET-AGENT-EXEC-01 (commit 1/2): `build_federated_node` принимает опц. `agent_executor`.
    - Если `orchestrator` передан (существующие вызовы) — используется КАК ЕСТЬ (обратная
      совместимость; executor внедряется вызывающим до построения orchestrator'а).
    - Если `orchestrator is None` — строит ReferenceOrchestrator через `build_orchestrator`
      из `identity_registry`/`plugin_registry`/`action_log` + `agent_executor` (reuse, НЕ
      дублирует логику сборки). Это и есть «сборка удалённого узла принимает agent_executor»:
      сервер исполняет agent-routed цели РЕАЛЬНЫМ agent tick'ом, trust эволюционирует из
      реального исхода.

    K5: reuses build_remote_orchestrator (client) + build_remote_execution_listener (server)
    + build_orchestrator; does NOT duplicate them. Standalone factory — НЕ in build_kernel.
    O1: server does not mutate remote trust; the client updates local trust from real outcomes.
    Детерминизм (I-09): LLM-free agent tick по умолчанию + correlation request_id в сети.
    """
    # ТЗ-NET-AGENT-EXEC-01 commit 2: если orchestrator не передан — построить с agent_executor
    # (reuse build_orchestrator; НЕ дублирует). Иначе использовать переданный (backward-compat).
    if orchestrator is None:
        if identity_registry is None or plugin_registry is None or action_log is None:
            raise ValueError(
                "build_federated_node: when orchestrator is None, provide "
                "identity_registry, plugin_registry, action_log (+ agent_executor)"
            )
        orchestrator = build_orchestrator(
            identity_registry, plugin_registry, trust, action_log,
            trust_threshold=trust_threshold, trust_delta=trust_delta,
            remote_nodes=remote_nodes, agent_executor=agent_executor,
        )
    client = build_remote_orchestrator(
        transport, trust, trust_threshold=trust_threshold,
        trust_delta=trust_delta, local_node_id=node_id,
        signature_provider=signature_provider, replay_guard=replay_guard,
        routing_table=routing_table, direct_peers=direct_peers,
    )
    server = build_remote_execution_listener(
        transport, orchestrator, node_id,
        signature_provider=signature_provider, replay_guard=replay_guard,
    )

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

