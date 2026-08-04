"""Reference federated orchestrator (ТЗ-FED-ORCH-01 client + ТЗ-FED-EXEC-01 wire, ADR-075/076).

K5 (commit 0): НЕ дублирует INetworkTransport (NW-01) — переиспользует КАК carrier через
send_facts(List[dict], node_id) / on_facts(handler). RemoteGoalRequest / RemoteOutcomeResponse
сериализуются в dict-конверты и коррелируются по request_id. Тесты детерминированы через
FakeTransport (in tests): send_facts синхронно дёргает on_facts с преднастроенным ответом узла.

ТЗ-FED-EXEC-01 (commit 1): wire-формат централизован в contracts/i_federated_orchestrator.py
(REQ_MARKER/RESP_MARKER + encode_*/decode_*). Этот client (ReferenceRemoteOrchestrator) и сервер
(ReferenceRemoteExecutionListener, kernel/federated_executor.py) используют ОДИН формат (K5,
single-source-of-truth, НЕ дублируют). Рефактор на shared helpers — behaviour-preserving (формат
конверта идентичен), доказано FED-ORCH-01 тестами.

Trust (IDT-01): dispatch_remote ВЫПОЛНЯЕТСЯ ТОЛЬКО если current_trust(node_id) >= threshold
(trust-gating; current_trust = LATEST, НЕ trust_score_of = MAX -> закрывает Флаг 1 IDT-01).
После получения РЕАЛЬНОГО outcome -> record_outcome(node_id, success, delta) -> trust
ЭВОЛЮЦИОНИРУЕТ из реального исхода; failure РЕАЛЬНО понижает (закрывает Флаг 2 ORCH-01:
agent-dispatch больше не always-success).

O1: trust-обновления SOFT (через ITrustRegistry); remote НЕ мутирует HARD/FSM локально.
I-09: детерминизм — correlation по request_id; FakeTransport синхронен в тестах.
Флаг C: build_remote_orchestrator — standalone фабрика, НЕ в build_kernel.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import time

from contracts.i_federated_orchestrator import (
    REQ_MARKER,
    RESP_MARKER,
    IRemoteOrchestrator,
    RemoteGoalRequest,
    RemoteOutcomeResponse,
    decode_outcome_response,
    encode_goal_request,
    encode_outcome_response,
    is_outcome_response,
)
from contracts.i_identity import ITrustRegistry
from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome

# Backwards-compat private aliases (ТЗ-FED-ORCH-01 tests / external callers may import these).
_REQ_KEY = REQ_MARKER
_RESP_KEY = RESP_MARKER


class ReferenceRemoteOrchestrator(IRemoteOrchestrator):
    """Deterministic remote orchestrator over INetworkTransport + ITrustRegistry.

    Carrier: send_facts/on_facts (NW-01). The local node sends a RemoteGoalRequest envelope
    and awaits the correlated RemoteOutcomeResponse via the on_facts subscription. Wire format
    is centralized in contracts/i_federated_orchestrator.py (K5 single-source-of-truth).
    """

    def __init__(
        self,
        transport: INetworkTransport,
        trust: ITrustRegistry,
        trust_threshold: float = 0.2,
        trust_delta: float = 0.1,
        local_node_id: str = "local",
        response_timeout: float = 2.0,
    ) -> None:
        self._t = transport
        self._trust = trust
        self._threshold = trust_threshold
        self._delta = trust_delta
        self._local = local_node_id
        self._response_timeout = response_timeout  # SOFT tunable (O1, runtime reflection)
        self._pending: Dict[str, dict] = {}
        self._t.on_facts(self._on_facts)

    def dispatch_remote(self, node_id: str, goal: OrchestrationGoal) -> TaskOutcome:
        # Trust-gating: only dispatch to nodes with LATEST trust >= threshold.
        if self._trust.current_trust(node_id) < self._threshold:
            return TaskOutcome(success=False, detail=f"low-trust node excluded: {node_id}")
        request_id = f"req:{node_id}:{goal.goal_id}"
        self._pending[request_id] = {}
        envelope = encode_goal_request(
            RemoteGoalRequest(
                request_id=request_id,
                node_id=node_id,
                goal=goal,
                author_id=self._local,
                causal=None,
            )
        )
        # Carrier: ship the request via NW-01 send_facts (broadcast; remote node responds).
        self._t.send_facts([envelope], self._local)
        # Deterministic WAIT for the correlated response (ТЗ-FED-TCP-01 / FSE-01 timing lesson):
        # over real TCP the remote execution + response round-trips asynchronously, so we poll
        # the pending holder (with a soft timeout) until the outcome lands — NOT a synchronous
        # assume. In-process SyncTransport resolves within one poll; real TCP resolves after the
        # network round-trip. Poll (short sleeps), NOT wall-clock sleep-luck.
        outcome = self._wait_for_outcome(request_id, timeout=self._response_timeout)
        if outcome is None:
            self._pending.pop(request_id, None)
            return TaskOutcome(success=False, detail=f"no remote response from {node_id}")
        # Trust evolves from the REAL remote outcome (success +, failure -).
        self._trust.record_outcome(node_id, outcome.success, self._delta)
        return outcome

    def _wait_for_outcome(self, request_id: str, timeout: float) -> Optional[TaskOutcome]:
        """Deterministic barrier: poll the pending holder until the correlated outcome arrives.

        Returns the TaskOutcome, or None on timeout. Polls (short sleeps) — does not busy-spin
        and does not assume synchronous transport delivery (real TCP round-trips async).
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            holder = self._pending.get(request_id)
            if holder is not None and "outcome" in holder:
                return holder["outcome"]
            time.sleep(0.01)
        return None

    def _on_facts(self, facts: List[dict], sender_node_id: str) -> None:
        for fact in facts:
            if not is_outcome_response(fact):
                continue
            request_id = fact["request_id"]
            holder = self._pending.get(request_id)
            if holder is None:
                continue
            holder["outcome"] = decode_outcome_response(fact).outcome


def build_remote_orchestrator(
    transport: INetworkTransport,
    trust: ITrustRegistry,
    trust_threshold: float = 0.2,
    trust_delta: float = 0.1,
    local_node_id: str = "local",
    response_timeout: float = 2.0,
) -> ReferenceRemoteOrchestrator:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return ReferenceRemoteOrchestrator(
        transport, trust, trust_threshold=trust_threshold,
        trust_delta=trust_delta, local_node_id=local_node_id,
        response_timeout=response_timeout,
    )
