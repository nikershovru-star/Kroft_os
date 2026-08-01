"""RetryManager — IRetryManager (Wave 10, ADR-013 Phase F).

Core rule (ADR-013 §2.4): a retry is NOT a repeat. Re-sending an identical query
to the same route burns budget for the same answer. The manager rewrites the
query and the PolicyContext tags so the PolicyEngine (Wave 5) is pushed toward a
DIFFERENT route on each attempt:

    attempt 2 -> reasoning=True   ("think harder")
    attempt 3 -> local=True       ("different provider entirely")

The escalation ladder is data, not branching, so v1.0 can extend it (or make it
failure-reason aware) without touching the executor.

Imports contracts only.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, Sequence, Tuple

from contracts.i_llm import ModelQuery
from contracts.i_policy import PolicyContext
from contracts.i_workflow import IRetryManager, Step

DEFAULT_MAX_ATTEMPTS = 3

# attempt number -> (ModelQuery field overrides, PolicyContext tag overrides)
DEFAULT_LADDER: Tuple[Tuple[Dict[str, object], Dict[str, str]], ...] = (
    ({"reasoning": True}, {"retry_strategy": "reasoning"}),
    ({"local": True}, {"retry_strategy": "local"}),
)


class RetryManager(IRetryManager):
    """Bounded retries that change the route rather than repeat it.

    Args:
        max_attempts: total attempts allowed per step (including the first).
        ladder: escalation table; entry N applies to attempt N+2.
    """

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        ladder: Sequence[Tuple[Dict[str, object], Dict[str, str]]] = DEFAULT_LADDER,
    ) -> None:
        self.max_attempts = max(1, int(max_attempts))
        self._ladder = tuple(ladder)

    # --- IRetryManager -----------------------------------------------------
    def should_retry(self, step: Step) -> bool:
        """True while the step still has attempts left."""
        return step.attempts < self.max_attempts

    def prepare_retry(
        self,
        query: ModelQuery,
        context: PolicyContext,
        attempt: int,
    ) -> Tuple[ModelQuery, PolicyContext]:
        """Return a MODIFIED (query, context) aimed at a different route.

        `attempt` is 1-based and refers to the attempt about to be made, so the
        first retry is attempt=2 and takes ladder[0].
        """
        rung = attempt - 2
        if rung < 0:
            # attempt 1 is not a retry: hand back the inputs untouched
            return query, context

        overrides, tags = self._ladder[min(rung, len(self._ladder) - 1)]

        new_query = replace(query, **overrides)
        merged_tags = dict(context.tags)
        merged_tags.update(tags)
        merged_tags["retry_attempt"] = str(attempt)
        new_context = replace(context, query=new_query, tags=merged_tags)
        return new_query, new_context

    def explain(self, attempt: int) -> str:
        """Human-readable description of what the next attempt changes (LAW 4)."""
        rung = attempt - 2
        if rung < 0:
            return f"attempt {attempt}: initial route"
        _overrides, tags = self._ladder[min(rung, len(self._ladder) - 1)]
        strategy = tags.get("retry_strategy", "unchanged")
        return f"attempt {attempt}: retry via '{strategy}' route"
