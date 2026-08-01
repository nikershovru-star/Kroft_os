"""Recovery backoff strategies — policy-driven (NOT hard-coded in the caller).

Per Phase 4: restart delays must come from config, not be hard-coded as
1/2/4/8/16/32/60. A BackoffStrategy computes the delay for a given attempt number.
Imports ONLY contracts + stdlib (arch-gate LAW K8).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BackoffStrategy(Protocol):
    """Computes the wait (seconds) before restart attempt `attempt` (1-based)."""

    def delay_for(self, attempt: int) -> float: ...
    def name(self) -> str: ...


class ConstantBackoff:
    def __init__(self, delay: float = 1.0) -> None:
        self._delay = delay

    def delay_for(self, attempt: int) -> float:
        return float(self._delay)

    def name(self) -> str:
        return "constant"


class LinearBackoff:
    def __init__(self, initial: float = 1.0, step: float = 1.0, max_delay: float = 60.0) -> None:
        self._initial = initial
        self._step = step
        self._max = max_delay

    def delay_for(self, attempt: int) -> float:
        return min(self._max, self._initial + self._step * max(0, attempt - 1))

    def name(self) -> str:
        return "linear"


class ExponentialBackoff:
    def __init__(self, initial: float = 1.0, factor: float = 2.0, max_delay: float = 60.0) -> None:
        self._initial = initial
        self._factor = factor
        self._max = max_delay

    def delay_for(self, attempt: int) -> float:
        import math
        return min(self._max, self._initial * (self._factor ** max(0, attempt - 1)))

    def name(self) -> str:
        return "exponential"
