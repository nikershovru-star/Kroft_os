"""Reference federated orchestrator (ТЗ-FED-ORCH-01, ADR-075) — deterministic, LLM-free.

K5 (commit 0): НЕ дублирует INetworkTransport (NW-01) — переиспользует КАК carrier через
send_facts(List[dict], node_id) / on_facts(handler). RemoteGoalRequest / RemoteOutcomeResponse
сериализуются в dict-конверты и коррелируются по request_id. Тесты детерминированы через
FakeTransport (in tests): send_facts синхронно дёргает on_facts с преднастроенным ответом узла.

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

import json
from typing import Callable, Dict, List, Optional, Tuple

from contracts.i_federated_orchestrator import (
    IRemoteOrchestrator,
    RemoteGoalRequest,
    RemoteOutcomeResponse,
)
from contracts.i_identity import ITrustRegistry
from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome

_REQ_KEY = "__fed_orch_req__"
_RESP_KEY = "__fed_orch_resp__"


def _request_to_dict(req: RemoteGoalRequest) -> dict:
    goal = req.goal
    causal = req.causal.to_dict() if req.causal is not None and hasattr(req.causal, "to_dict") else None
    return {
        _REQ_KEY: True,
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


def _response_to_dict(resp: RemoteOutcomeResponse) -> dict:
    causal = resp.causal.to_dict() if resp.causal is not None and hasattr(resp.causal, "to_dict") else None
    return {
        _RESP_KEY: True,
        "request_id": resp.request_id,
        "node_id": resp.node_id,
        "author_id": resp.author_id,
        "causal": causal,
        "outcome": {"success": resp.outcome.success, "detail": resp.outcome.detail},
    }


def _dict_to_goal(d: dict) -> OrchestrationGoal:
    return OrchestrationGoal(
        goal_id=d["goal_id"],
        capability=d["capability"],
        required_permission=d.get("required_permission"),
        payload=d.get("payload"),
    )


class ReferenceRemoteOrchestrator(IRemoteOrchestrator):
    """Deterministic remote orchestrator over INetworkTransport + ITrustRegistry.

    Carrier: send_facts/on_facts (NW-01). The local node sends a RemoteGoalRequest envelope
    and awaits the correlated RemoteOutcomeResponse via the on_facts subscription.
    """

    def __init__(
        self,
        transport: INetworkTransport,
        trust: ITrustRegistry,
        trust_threshold: float = 0.2,
        trust_delta: float = 0.1,
        local_node_id: str = "local",
    ) -> None:
        self._t = transport
        self._trust = trust
        self._threshold = trust_threshold
        self._delta = trust_delta
        self._local = local_node_id
        self._pending: Dict[str, dict] = {}
        self._t.on_facts(self._on_facts)

    def dispatch_remote(self, node_id: str, goal: OrchestrationGoal) -> TaskOutcome:
        # Trust-gating: only dispatch to nodes with LATEST trust >= threshold.
        if self._trust.current_trust(node_id) < self._threshold:
            return TaskOutcome(success=False, detail=f"low-trust node excluded: {node_id}")
        request_id = f"req:{node_id}:{goal.goal_id}"
        self._pending[request_id] = {}
        envelope = _request_to_dict(
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
        # Deterministic reference path: the transport delivers the response synchronously
        # (FakeTransport in tests calls on_facts immediately). If not resolved -> failure.
        holder = self._pending.get(request_id)
        if holder is None or "outcome" not in holder:
            return TaskOutcome(success=False, detail=f"no remote response from {node_id}")
        outcome: TaskOutcome = holder["outcome"]
        del self._pending[request_id]
        # Trust evolves from the REAL remote outcome (success +, failure -).
        self._trust.record_outcome(node_id, outcome.success, self._delta)
        return outcome

    def _on_facts(self, facts: List[dict], sender_node_id: str) -> None:
        for fact in facts:
            if not isinstance(fact, dict) or not fact.get(_RESP_KEY):
                continue
            request_id = fact["request_id"]
            holder = self._pending.get(request_id)
            if holder is None:
                continue
            holder["outcome"] = TaskOutcome(
                success=fact["outcome"]["success"], detail=fact["outcome"]["detail"]
            )


def build_remote_orchestrator(
    transport: INetworkTransport,
    trust: ITrustRegistry,
    trust_threshold: float = 0.2,
    trust_delta: float = 0.1,
    local_node_id: str = "local",
) -> ReferenceRemoteOrchestrator:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return ReferenceRemoteOrchestrator(
        transport, trust, trust_threshold=trust_threshold,
        trust_delta=trust_delta, local_node_id=local_node_id,
    )
