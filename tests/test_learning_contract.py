"""contracts/test_learning_contract.py — ports abstract, entities frozen (Wave 12).

Verifies LAW 1 (contracts only) and LAW 3 (immutability) for the learning layer.
"""
from __future__ import annotations

import abc
import inspect

from contracts.i_learning import (
    ExecutionTrace,
    ILearningStore,
    IPatternExtractor,
    Pattern,
    StepTrace,
)


def test_ports_are_abstract() -> None:
    for cls in (ILearningStore, IPatternExtractor):
        assert inspect.isabstract(cls)
        # every method must be abstract
        for name, meth in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("__"):
                assert getattr(meth, "__isabstractmethod__", False), name


def test_step_trace_frozen() -> None:
    s = StepTrace(step_id="s1", model_id="phi4", prompt="p", output="o", eval_score=0.9)
    assert s.eval_score == 0.9
    try:
        s.eval_score = 0.1  # type: ignore[misc]
        raise AssertionError("StepTrace is mutable")
    except (AttributeError, TypeError):
        pass


def test_execution_trace_frozen() -> None:
    t = ExecutionTrace(trace_id="t1", goal="g", workflow_id="w")
    try:
        t.goal = "x"  # type: ignore[misc]
        raise AssertionError("ExecutionTrace is mutable")
    except (AttributeError, TypeError):
        pass
    # nested steps are also frozen
    try:
        t.steps[0] = None  # type: ignore[index, misc]
        raise AssertionError("steps tuple is mutable")
    except (TypeError, AttributeError):
        pass


def test_pattern_frozen() -> None:
    p = Pattern("d", 0.5, ("reasoning",), "use phi4")
    try:
        p.confidence = 0.9  # type: ignore[misc]
        raise AssertionError("Pattern is mutable")
    except (AttributeError, TypeError):
        pass


def test_illegal_state_method_absent() -> None:
    # LAW 3: no update()/mutators on trace entities
    for cls in (ExecutionTrace, StepTrace, Pattern):
        assert not any(n.startswith("update") or n.startswith("set_") for n in dir(cls))


def test_ilearningstore_not_instantiable() -> None:
    try:
        ILearningStore()  # type: ignore[abstract]
        raise AssertionError("ILearningStore instantiated")
    except TypeError:
        pass


def test_ipattern_extractor_not_instantiable() -> None:
    try:
        IPatternExtractor()  # type: ignore[abstract]
        raise AssertionError("IPatternExtractor instantiated")
    except TypeError:
        pass
