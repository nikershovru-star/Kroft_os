"""Recovery policy — declarative, config-driven restart rules.

Per Phase 4: different components have different policies. A RecoveryPolicy is a
frozen dataclass built from a dict (e.g. parsed from YAML). The Supervisor reads
`max_attempts`, `initial_delay`, `max_delay`, `strategy` — never hard-coded.

Examples:
  Database:        {restart: true,  max_attempts: 10}
  LLM Worker:      {restart: true,  max_attempts: 3}
  Human approval:  {restart: false}

Imports ONLY contracts + stdlib (arch-gate LAW K8).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RecoveryPolicy:
    """Immutable, config-driven restart policy for one component."""

    restart: bool = True
    max_attempts: int = 5
    initial_delay: float = 1.0
    max_delay: float = 60.0
    strategy: str = "exponential"  # constant | linear | exponential

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryPolicy":
        restart = data.get("restart", True)
        # 'restart: false' may be a bare bool or nested under a 'restart' mapping.
        if isinstance(restart, dict):
            restart = restart.get("enabled", True)
        return cls(
            restart=bool(restart),
            max_attempts=int(data.get("max_attempts", 5)),
            initial_delay=float(data.get("initial_delay", 1.0)),
            max_delay=float(data.get("max_delay", 60.0)),
            strategy=str(data.get("strategy", "exponential")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "restart": self.restart,
            "max_attempts": self.max_attempts,
            "initial_delay": self.initial_delay,
            "max_delay": self.max_delay,
            "strategy": self.strategy,
        }

    def should_quarantine(self, attempt: int) -> bool:
        """After max_attempts exhausted, quarantine instead of looping forever."""
        return self.restart and attempt > self.max_attempts
