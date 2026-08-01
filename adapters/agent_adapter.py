"""Agent adapters (Stage 33)."""
from __future__ import annotations

from typing import Any, Dict

from contracts import IAgent


class RuleBasedAgentAdapter(IAgent):
    """Default rule-based agent (zero external deps)."""

    def __init__(self, agent_service: "AgentService") -> None:  # noqa: F821
        self._svc = agent_service

    def execute(self, command: str) -> Dict[str, Any]:
        return self._svc.execute(command)
