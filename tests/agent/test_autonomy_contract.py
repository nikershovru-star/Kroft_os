"""contracts/test_autonomy_contract.py — ports abstract, entities frozen (Wave 14).

Verifies LAW 1 (contracts only) and LAW 3 (immutability) for the autonomy layer.
"""
from __future__ import annotations

import abc
import inspect

from contracts.i_autonomy import (
    DocSyncResult,
    EvaluationReport,
    IAutonomyController,
    IDocMaintainer,
    ISelfEvaluator,
)


def test_ports_are_abstract() -> None:
    for cls in (IAutonomyController, ISelfEvaluator, IDocMaintainer):
        assert inspect.isabstract(cls)
        for name, meth in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("__"):
                assert getattr(meth, "__isabstractmethod__", False), name


def test_evaluation_report_frozen() -> None:
    r = EvaluationReport(timestamp="t", plan_success_rate=0.9, pattern_drift=0.5, optimization_yield=0.7)
    try:
        r.plan_success_rate = 0.1  # type: ignore[misc]
        raise AssertionError("EvaluationReport is mutable")
    except (AttributeError, TypeError):
        pass


def test_doc_sync_result_frozen() -> None:
    d = DocSyncResult(mismatches=("x",), proposed_diffs=("y",))
    try:
        d.mismatches = ()  # type: ignore[misc]
        raise AssertionError("DocSyncResult is mutable")
    except (AttributeError, TypeError):
        pass


def test_no_illegal_mutators_on_entities() -> None:
    for cls in (EvaluationReport, DocSyncResult):
        assert not any(n.startswith("update") or n.startswith("set_") for n in dir(cls))


def test_abstract_not_instantiable() -> None:
    for cls in (IAutonomyController, ISelfEvaluator, IDocMaintainer):
        try:
            cls()  # type: ignore[abstract]
            raise AssertionError(f"{cls.__name__} instantiated")
        except TypeError:
            pass
