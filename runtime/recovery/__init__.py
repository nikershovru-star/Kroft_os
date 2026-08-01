"""runtime.recovery — Autonomous Runtime Recovery Layer (Phase 4).

Policy-driven backoff, recovery state, and the recovery journal. Depends ONLY on
contracts + stdlib (arch-gate LAW K8). No platform/adapters/plugins imports.
"""
from __future__ import annotations

from runtime.recovery.backoff import (
    BackoffStrategy,
    ConstantBackoff,
    ExponentialBackoff,
    LinearBackoff,
)
from runtime.recovery.policy import RecoveryPolicy
from runtime.recovery.strategy import build_strategy
from runtime.recovery.recovery_journal import RecoveryJournal
from runtime.recovery.recovery_state import RecoveryState

__all__ = [
    "BackoffStrategy",
    "ConstantBackoff",
    "LinearBackoff",
    "ExponentialBackoff",
    "RecoveryPolicy",
    "build_strategy",
    "RecoveryJournal",
    "RecoveryState",
]
