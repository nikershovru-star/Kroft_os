"""StepReflection — IReflection heuristic (Wave 10, ADR-013 Phase F).

v0.1 is openly a heuristic: it separates "empty / truncated" from "there is
something here", and does NOT pretend to judge meaning. A rubric-based LLM judge
is v1.0.

What matters architecturally is LAW 5: the score is ALWAYS recorded, including
on rejection. Without accumulated numbers there is nothing for v1.0 to be
compared against.

Imports contracts only — a service may not import adapters or sibling services.
"""
from __future__ import annotations

from typing import Optional

from contracts.i_eval import Scorecard
from contracts.i_workflow import IReflection, Step

DEFAULT_MIN_LENGTH = 20
DEFAULT_ACCURACY_KEY = "accuracy"


class StepReflection(IReflection):
    """Heuristic acceptance check for a step's output.

    Args:
        min_length: minimum characters for an output to count as substantive.
        min_score: acceptance threshold on the computed score.
        accuracy_key: metric read from a Scorecard when one is supplied.
    """

    def __init__(
        self,
        min_length: int = DEFAULT_MIN_LENGTH,
        min_score: float = 0.5,
        accuracy_key: str = DEFAULT_ACCURACY_KEY,
    ) -> None:
        self.min_length = min_length
        self.min_score = min_score
        self.accuracy_key = accuracy_key

    # --- IReflection -------------------------------------------------------
    def score(self, step: Step, scorecard: Optional[Scorecard] = None) -> float:
        """Measured quality in [0.0, 1.0].

        With a Scorecard (Wave 7) the measured accuracy wins — that is real
        evidence. Without one we fall back to the length heuristic, which is
        honest about being a proxy.
        """
        if scorecard is not None:
            measured = scorecard.metrics.get(self.accuracy_key)
            if measured is not None:
                return max(0.0, min(1.0, float(measured)))

        text = (step.output or "").strip()
        if not text:
            return 0.0
        if len(text) < self.min_length:
            # partial credit: something came back, but it is a stub
            return round(min(0.49, len(text) / (self.min_length * 2.0)), 4)
        return 1.0

    def evaluate_step(self, step: Step, scorecard: Optional[Scorecard] = None) -> bool:
        """True when the step's output is good enough to move on."""
        if step.error:
            return False
        return self.score(step, scorecard) >= self.min_score

    def explain(self, step: Step, scorecard: Optional[Scorecard] = None) -> str:
        """Human-readable justification (LAW 4)."""
        value = self.score(step, scorecard)
        verdict = "accepted" if self.evaluate_step(step, scorecard) else "rejected"
        basis = "scorecard" if scorecard is not None else "heuristic"
        if step.error:
            return f"step '{step.id}' {verdict} (error: {step.error})"
        return (
            f"step '{step.id}' {verdict} "
            f"(score {value:.2f} vs threshold {self.min_score:.2f}, basis: {basis})"
        )
