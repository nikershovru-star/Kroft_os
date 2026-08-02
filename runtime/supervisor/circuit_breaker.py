"""Circuit Breaker for agent/component recovery (Wave 2 WP-10, ADR-038).

K8-compliant: imports ONLY contracts + runtime + stdlib. No services/adapters
imports (verified by arch-gate). Reuses runtime.recovery.backoff for the
HALF_OPEN cooldown timer.

States: CLOSED -> OPEN (failure_threshold consecutive failures) -> HALF_OPEN
(cooldown elapsed) -> CLOSED (1 success probe) | OPEN (1 failure probe).
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Optional

from runtime.recovery.backoff import BackoffStrategy, ExponentialBackoff


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Bounded failure detector that trips open and probes for recovery."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_strategy: Optional[BackoffStrategy] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._name = name
        self._threshold = failure_threshold
        self._strategy = cooldown_strategy or ExponentialBackoff(initial=1.0, factor=2.0, max_delay=60.0)
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._trip_count = 0
        self._opened_at: float = 0.0
        self._attempt = 0  # cooldown attempt counter for the backoff strategy

    # -- API ---------------------------------------------------------------

    @property
    def current_state(self) -> CircuitState:
        # Auto-transition OPEN -> HALF_OPEN once cooldown elapsed.
        if self._state is CircuitState.OPEN and self._clock() >= self._opened_at + self._cooldown():
            self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def trip_count(self) -> int:
        return self._trip_count

    def allow_request(self) -> bool:
        """Call before an operation. OPEN blocks; HALF_OPEN allows a probe."""
        return self.current_state is not CircuitState.OPEN

    def on_success(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._attempt = 0

    def on_failure(self) -> None:
        self._consecutive_failures += 1
        if self._state is CircuitState.HALF_OPEN:
            self._trip()  # probe failed -> reopen
            return
        if self._consecutive_failures >= self._threshold:
            self._trip()

    # -- helpers -----------------------------------------------------------

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._attempt += 1
        self._trip_count += 1
        self._consecutive_failures = 0

    def _cooldown(self) -> float:
        return self._strategy.delay_for(self._attempt)
