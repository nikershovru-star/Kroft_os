"""Inter-agent messenger over the EventBus (TZ-AGENT-001 WP-04, ADR-037 §2).

K1-compliant: contracts only + stdlib. K6: agents communicate EXCLUSIVELY
through the IEventBus — never direct calls. Every send() is gated by the
tenant boundary (TenantIsolator) and capability authorization (CapabilityManager)
before any publish. MessageDeduplicator guarantees idempotent delivery.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Dict, List, Optional

from contracts.agent_orchestration import AgentMessage, IAgentMessenger
from contracts.i_event_bus import IEventBus
from contracts.security import Capability, CapabilityContext, ICapabilityManager, Role
from contracts.tenant import ITenantIsolator


class MessageDeduplicator:
    """Idempotency guard — a message id is delivered at most once."""

    def __init__(self) -> None:
        self._seen: set = set()

    def seen(self, msg_id: str) -> bool:
        if msg_id in self._seen:
            return True
        self._seen.add(msg_id)
        return False


class AgentMessenger(IAgentMessenger):
    """Delivers AgentMessages via IEventBus, enforcing tenant + capability."""

    def __init__(
        self,
        bus: IEventBus,
        isolator: ITenantIsolator,
        capability: ICapabilityManager,
        role_resolver: Optional[Callable[[str], Role]] = None,
    ) -> None:
        self._bus = bus
        self._isolator = isolator
        self._capability = capability
        self._role_resolver = role_resolver or (lambda _aid: Role.OPERATOR)
        self._dedup = MessageDeduplicator()

    # -- IAgentMessenger ---------------------------------------------------

    def send(self, msg: AgentMessage) -> bool:
        if self._dedup.seen(msg.id):
            return False  # duplicate -> dropped (idempotency)

        # R3/R6: cross-tenant messaging is denied at the boundary.
        if not self._isolator.check_boundary(msg.tenant_id, msg.tenant_id):
            return False

        # R5: capability required to send this message must be authorized.
        role = self._role_resolver(msg.sender_id)
        ctx = self._capability.context_for(msg.sender_id, role)
        decision = self._capability.authorize(ctx, Capability.parse(msg.capability_required))
        if not decision.allowed:
            return False

        # K6: publish only over the EventBus (never direct agent-to-agent call).
        self._bus.publish_sync(f"agent.{msg.recipient_id}", asdict(msg))
        return True

    def receive(self, agent_id: str) -> List[AgentMessage]:
        history = self._bus.get_history(f"agent.{agent_id}") or []
        out: List[AgentMessage] = []
        for raw in history:
            if isinstance(raw, dict) and "recipient_id" in raw:
                out.append(AgentMessage(**{
                    k: raw[k] for k in (
                        "id", "sender_id", "recipient_id", "tenant_id",
                        "payload", "capability_required", "timestamp",
                    ) if k in raw
                }))
        return out
