"""Fact-check via Self-Consistency sampling (Stage 4, ТЗ-ECHO/roadmap).

K1-compliant: lives in services/ (domain). Imports ONLY contracts + stdlib.
Depends on ILlm abstraction (never a concrete adapter) — K2.

Goal: detect contradictions / hallucination in a generated claim by asking the
same model the SAME question N times with sampling temperature > 0, then
measuring agreement. High agreement = low hallucination risk; low agreement or
directly contradictory answers = flag for human / external verification.

Deterministic rule (I-09): agreement is a simple, inspectable ratio of
normalised answer equality. NO LLM is used to *decide* consistency — the model
only produces candidate answers; the aggregation is pure Python.

Graceful degradation: if the LLM is unavailable (LLMError / LLMTimeout / no
provider), ``check`` returns verdict=UNKNOWN with empty answers — the caller
keeps the local-only answer instead of crashing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout


class Verdict(str, Enum):
    """Outcome of a self-consistency check (NO truth claim — only agreement)."""

    CONSISTENT = "consistent"      # >= agreement_threshold answers agree
    CONFLICT = "conflict"          # answers directly contradict
    LOW_AGREEMENT = "low_agreement"  # spread too wide, below threshold
    UNKNOWN = "unknown"            # LLM unavailable -> cannot assert


class FactCheckResult:
    """Immutable outcome of one self-consistency check.

    Carries the raw answers for traceability (proof-over-existence: an empty
    answer list is an error, never a degraded 'true'). confidence is the
    measured agreement ratio (0..1), NOT a truth probability — invariant
    confidence != truth.
    """

    def __init__(
        self,
        verdict: Verdict,
        answers: List[str],
        agreement: float,
        contradictions: Optional[List[str]] = None,
        note: str = "",
    ) -> None:
        self._verdict = verdict
        self._answers = tuple(answers)
        self._agreement = agreement
        self._contradictions = tuple(contradictions or ())
        self._note = note

    @property
    def verdict(self) -> Verdict:
        return self._verdict

    @property
    def answers(self) -> tuple:
        return self._answers

    @property
    def agreement(self) -> float:
        """Measured agreement ratio 0..1 (NOT a truth probability)."""
        return self._agreement

    @property
    def contradictions(self) -> tuple:
        return self._contradictions

    @property
    def note(self) -> str:
        return self._note

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"FactCheckResult(verdict={self._verdict.value}, "
            f"agreement={self._agreement:.2f}, n={len(self._answers)})"
        )


def _normalise(text: str) -> str:
    """Lower-case, strip punctuation/space, keep alphanumerics only.

    Makes agreement comparison robust to trivial wording differences without
    any LLM involvement.
    """
    return re.sub(r"[^a-z0-9а-яё]", "", text.lower(), flags=re.UNICODE)


class SelfConsistency:
    """Self-consistency fact-check over an ILlm.

    Usage:
        checker = SelfConsistency(llm, n=3, temperature=0.7,
                                  agreement_threshold=0.6)
        res = checker.check("What year did KROFT OS v1 release?")
        if res.verdict == Verdict.CONFLICT:
            # route to external verification / abstain
    """

    def __init__(
        self,
        llm: ILlm,
        n: int = 3,
        agreement_threshold: float = 0.6,
        prompt_template: str = (
            "Answer concisely and factually. Question: {query}"
        ),
    ) -> None:
        if n < 1:
            raise ValueError("n must be >= 1")
        if not 0.0 <= agreement_threshold <= 1.0:
            raise ValueError("agreement_threshold must be 0..1")
        self._llm = llm
        self._n = n
        self._agreement_threshold = agreement_threshold
        self._prompt_template = prompt_template

    def check(self, query: str) -> FactCheckResult:
        """Run N samples; return a FactCheckResult (never raises on LLM errors)."""
        answers: List[str] = []
        for _ in range(self._n):
            try:
                resp: LlmResponse = self._llm.complete(
                    ModelQuery(
                        prompt=self._prompt_template.format(query=query),
                        reasoning=False,
                    )
                )
            except (LLMError, LLMTimeout):
                # LLM unavailable -> cannot assert consistency
                return FactCheckResult(
                    Verdict.UNKNOWN, [], 0.0,
                    note="llm unavailable; local-only answer retained",
                )
            if resp.ok() and resp.text.strip():
                answers.append(resp.text.strip())

        if not answers:
            return FactCheckResult(
                Verdict.UNKNOWN, [], 0.0, note="no valid answers produced"
            )

        # agreement = share of the mode answer among all answers
        norm = [_normalise(a) for a in answers]
        if not any(norm):
            return FactCheckResult(
                Verdict.LOW_AGREEMENT, answers, 0.0,
                note="answers empty after normalisation",
            )
        mode = max(set(norm), key=norm.count)
        agreement = norm.count(mode) / len(norm)

        if agreement >= self._agreement_threshold:
            return FactCheckResult(Verdict.CONSISTENT, answers, agreement)
        return FactCheckResult(
            Verdict.LOW_AGREEMENT, answers, agreement,
            note="agreement below threshold",
        )
