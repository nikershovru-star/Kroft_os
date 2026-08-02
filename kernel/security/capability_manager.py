"""Capability Manager — RBAC + authorization core (TZ-SEC-001 WP-01/02/03).

K1-compliant: imports ONLY contracts (stdlib-only). This is the kernel-internal
clean logic. Heavy IO (secret storage, audit sink, terminal) lives in
services/security/* behind the ports defined in contracts/security.
"""
from __future__ import annotations

from typing import Dict, List

from contracts.security import (
    AuthDecision,
    Capability,
    CapabilityContext,
    ICapabilityManager,
    ICapabilityPolicy,
    Role,
)


# Default RBAC mapping (ADR-033). Operator/Admin get broader access.
_DEFAULT_ROLE_CAPS: Dict[Role, List[Capability]] = {
    Role.ARCHITECT: [
        Capability.parse("Planner.*"),
        Capability.parse("Memory.*"),
        Capability.parse("Graph.*"),
        Capability.parse("RAG.*"),
        Capability.parse("Tool.*"),
    ],
    Role.RESEARCHER: [
        Capability.parse("Memory.*"),
        Capability.parse("Graph.*"),
        Capability.parse("RAG.*"),
        Capability.parse("Network.*"),
        Capability.parse("Tool.*"),
    ],
    Role.CODER: [
        Capability.parse("Filesystem.*"),
        Capability.parse("Git.*"),
        Capability.parse("Python.*"),
        Capability.parse("Memory.*"),
        Capability.parse("Tool.*"),
    ],
    Role.ANALYST: [
        Capability.parse("Memory.*"),
        Capability.parse("Graph.*"),
        Capability.parse("RAG.*"),
        Capability.parse("Tool.*"),
    ],
    Role.REVIEWER: [
        Capability.parse("Filesystem.Read"),
        Capability.parse("Graph.*"),
        Capability.parse("Tool.*"),
    ],
    Role.MEMORY_AGENT: [
        Capability.parse("Memory.*"),
        Capability.parse("Graph.*"),
        Capability.parse("RAG.*"),
    ],
    Role.PLANNER: [
        Capability.parse("Planner.*"),
        Capability.parse("Memory.Read"),
        Capability.parse("Tool.*"),
    ],
    Role.OPERATOR: [
        Capability.parse("Shell.*"),
        Capability.parse("Filesystem.*"),
        Capability.parse("Git.*"),
        Capability.parse("Tool.*"),
    ],
    Role.ADMIN: [
        Capability.parse(c + ".*") for c in
        ["Tool", "Filesystem", "Network", "Memory", "RAG", "Graph",
         "Planner", "Shell", "Python", "Git", "Secrets", "Admin"]
    ],
}

# Capabilities that always require human approval (ADR-034).
_DANGEROUS = {
    "Filesystem.Delete",
    "Git.Push",
    "Git.Commit",
    "Python.Execute",
    "Shell.Execute",
    "Secrets.Read",
    "Secrets.Write",
    "Admin.*",
}


class CapabilityManager(ICapabilityManager):
    """In-memory RBAC + authorization (K1-clean)."""

    def __init__(self, roles: Dict[Role, List[Capability]] | None = None) -> None:
        self._roles = dict(_DEFAULT_ROLE_CAPS)
        if roles:
            self._roles.update(roles)
        self._extra_policies: List[ICapabilityPolicy] = []

    def register_role(self, role: Role, capabilities: List[Capability]) -> None:
        self._roles[role] = list(capabilities)

    def register_policy(self, policy: ICapabilityPolicy) -> None:
        self._extra_policies.append(policy)

    def context_for(self, agent_id: str, role: Role) -> CapabilityContext:
        granted = list(self._roles.get(role, []))
        return CapabilityContext(agent_id=agent_id, role=role, granted=granted)

    def authorize(self, ctx: CapabilityContext, required: Capability) -> AuthDecision:
        # Extra policies can veto/allow independently.
        for policy in self._extra_policies:
            d = policy.evaluate(ctx, required)
            if not d.allowed:
                return d

        # Grant check: does any granted capability match (category + op/wildcard)?
        matched = None
        for cap in ctx.granted:
            if cap.matches(required):
                matched = cap
                break

        if matched is None:
            return AuthDecision.deny(
                required,
                f"role {ctx.role.value} lacks capability {required.id}",
            )

        # Dangerous capability (granted but sensitive) -> approval required (ADR-034).
        if self._is_dangerous(required):
            return AuthDecision.needs_approval(required)

        return AuthDecision.allow(required)

    @staticmethod
    def _is_dangerous(cap: Capability) -> bool:
        key = f"{cap.category.value}.{cap.operation}"
        return key in _DANGEROUS
