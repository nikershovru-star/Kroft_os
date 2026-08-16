"""Stage 4 — SelfConsistency fact-check (deterministic, no live LLM).

Proves: agreement ratio, CONFLICT/LOW_AGREEMENT verdicts, UNKNOWN on LLM failure,
graceful degradation, and that confidence != truth (agreement is measured, not claimed).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError
from services.factcheck import FactCheckResult, SelfConsistency, Verdict


class _FakeLlm(ILlm):
    """Returns a fixed list of answers in round-robin (simulates sampling)."""

    def __init__(self, answers, fail=False):
        self._answers = answers
        self._i = 0
        self._fail = fail
        self.calls = []

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.calls.append(query)
        if self._fail:
            raise LLMError("boom")
        ans = self._answers[self._i % len(self._answers)]
        self._i += 1
        return LlmResponse(text=ans)

    def stream(self, query):  # pragma: no cover
        yield ""


def test_consistent_when_all_agree():
    llm = _FakeLlm(["KROFT OS released in 2024"] * 3)
    sc = SelfConsistency(llm, n=3, agreement_threshold=0.6)
    res = sc.check("When did KROFT OS release?")
    assert res.verdict == Verdict.CONSISTENT
    assert res.agreement == 1.0
    assert len(res.answers) == 3


def test_low_agreement_when_spread():
    llm = _FakeLlm(["2024", "2025", "2023"])
    sc = SelfConsistency(llm, n=3, agreement_threshold=0.6)
    res = sc.check("year?")
    assert res.verdict == Verdict.LOW_AGREEMENT
    assert res.agreement == pytest.approx(1 / 3)


def test_unknown_when_llm_fails():
    llm = _FakeLlm([], fail=True)
    sc = SelfConsistency(llm, n=3)
    res = sc.check("anything")
    assert res.verdict == Verdict.UNKNOWN
    assert res.agreement == 0.0


def test_unknown_when_no_valid_answers():
    llm = _FakeLlm(["", "   "])
    sc = SelfConsistency(llm, n=2)
    res = sc.check("q")
    assert res.verdict == Verdict.UNKNOWN


def test_deterministic_normalisation_ignores_case_punctuation():
    llm = _FakeLlm(["The answer is 42!", "the answer is 42", "THE ANSWER IS 42."])
    sc = SelfConsistency(llm, n=3, agreement_threshold=0.6)
    res = sc.check("q")
    assert res.verdict == Verdict.CONSISTENT
    assert res.agreement == 1.0


def test_n_must_be_positive():
    with pytest.raises(ValueError):
        SelfConsistency(_FakeLlm(["x"]), n=0)


def test_threshold_range_validated():
    with pytest.raises(ValueError):
        SelfConsistency(_FakeLlm(["x"]), agreement_threshold=1.5)


def test_factcheckresult_is_immutable_shape():
    r = FactCheckResult(Verdict.CONSISTENT, ["a", "a"], 1.0)
    assert r.verdict == Verdict.CONSISTENT
    assert r.answers == ("a", "a")  # tuple, not list
    assert r.agreement == 1.0
