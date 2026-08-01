"""Strategy factory — builds a BackoffStrategy from a policy name.

Decouples the policy string ("exponential") from the concrete backoff class.
Imports ONLY local recovery modules + stdlib (arch-gate LAW K8).
"""
from __future__ import annotations

from typing import Any, Dict

from runtime.recovery.backoff import (
    BackoffStrategy,
    ConstantBackoff,
    ExponentialBackoff,
    LinearBackoff,
)


def build_strategy(policy: Any) -> BackoffStrategy:
    """Return a BackoffStrategy matching policy.strategy / policy fields."""
    name = (getattr(policy, "strategy", "exponential") or "exponential").lower()
    initial = getattr(policy, "initial_delay", 1.0)
    max_delay = getattr(policy, "max_delay", 60.0)
    if name == "constant":
        return ConstantBackoff(delay=initial)
    if name == "linear":
        return LinearBackoff(initial=initial, step=initial, max_delay=max_delay)
    # default: exponential
    return ExponentialBackoff(initial=initial, factor=2.0, max_delay=max_delay)
