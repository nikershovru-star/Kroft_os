"""contracts/test_optimization_contract.py — ports abstract, entities frozen (Wave 13).

Verifies LAW 1 (contracts only) and LAW 3 (immutability) for the optimization layer.
"""
from __future__ import annotations

import abc
import inspect

from contracts.i_optimization import (
    REC_STATUS_PROPOSED,
    GUARD_APPROVED,
    GuardrailResult,
    IOptimizer,
    IGuardrail,
    Recommendation,
)


def test_ports_are_abstract() -> None:
    for cls in (IOptimizer, IGuardrail):
        assert inspect.isabstract(cls)
        for name, meth in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("__"):
                assert getattr(meth, "__isabstractmethod__", False), name


def test_recommendation_frozen() -> None:
    r = Recommendation(
        id="r1", target="policy:x:w", value="{}", rationale="r",
        confidence=0.9, source_pattern="phi4 better", status=REC_STATUS_PROPOSED,
    )
    assert r.confidence == 0.9
    try:
        r.confidence = 0.1  # type: ignore[misc]
        raise AssertionError("Recommendation is mutable")
    except (AttributeError, TypeError):
        pass


def test_guardrail_result_frozen() -> None:
    g = GuardrailResult(allowed=True, stage=GUARD_APPROVED, risk_score=0.1, explanation="ok")
    try:
        g.risk_score = 0.9  # type: ignore[misc]
        raise AssertionError("GuardrailResult is mutable")
    except (AttributeError, TypeError):
        pass


def test_no_illegal_mutators_on_entities() -> None:
    for cls in (Recommendation, GuardrailResult):
        assert not any(n.startswith("update") or n.startswith("set_") for n in dir(cls))


def test_recommendation_default_status_proposed() -> None:
    r = Recommendation(id="r", target="t", value="v", rationale="x", confidence=0.8, source_pattern="p")
    assert r.status == REC_STATUS_PROPOSED


def test_abstract_not_instantiable() -> None:
    for cls in (IOptimizer, IGuardrail):
        try:
            cls()  # type: ignore[abstract]
            raise AssertionError(f"{cls.__name__} instantiated")
        except TypeError:
            pass
