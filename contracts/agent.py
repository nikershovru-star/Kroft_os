"""IAgent — Hermes agent port (Stage 33)."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Tool:
    name: str
    fn: Callable[..., Any]
    description: str = ""
    required_capabilities: "List[str]" = field(default_factory=list)


class IAgent(abc.ABC):
    @abc.abstractmethod
    def execute(self, command: str) -> Dict[str, Any]:
        """Parse *command* and return {"plan": [...], "results": [...]}}."""
