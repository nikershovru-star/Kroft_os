"""services/test_config_applier.py — propose -> approve -> apply -> rollback (Wave 13).

Verifies the two-phase commit and history-based rollback (LAW 3 explicit state).
"""
from __future__ import annotations

import pytest

from contracts.i_optimization import REC_STATUS_APPLIED, REC_STATUS_APPROVED, REC_STATUS_ROLLED_BACK, Recommendation
from services.config_applier import ConfigApplier


def _rec(rec_id="r1", target="policy:ProviderSelectionPolicy:weights:reasoning", value='0.7'):
    return Recommendation(
        id=rec_id, target=target, value=value, rationale="r",
        confidence=0.9, source_pattern="phi4 better",
    )


def test_apply_requires_approve() -> None:
    applier = ConfigApplier()
    rid = applier.propose(_rec())
    target = {"policy": {"ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}}}}
    assert applier.apply(rid, target) is False  # not approved yet
    assert target["policy"]["ProviderSelectionPolicy"]["weights"]["reasoning"] == 0.5


def test_full_lifecycle() -> None:
    applier = ConfigApplier()
    rid = applier.propose(_rec())
    assert applier.approve(rid, approved_by="tester") is True
    target = {"policy": {"ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}}}}
    assert applier.apply(rid, target) is True
    assert target["policy"]["ProviderSelectionPolicy"]["weights"]["reasoning"] == 0.7
    assert applier.status(rid) == REC_STATUS_APPLIED


def test_rollback_restores_previous() -> None:
    applier = ConfigApplier()
    rid = applier.propose(_rec())
    applier.approve(rid)
    target = {"policy": {"ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}}}}
    applier.apply(rid, target)
    assert target["policy"]["ProviderSelectionPolicy"]["weights"]["reasoning"] == 0.7
    assert applier.rollback(rid, target) is True
    assert target["policy"]["ProviderSelectionPolicy"]["weights"]["reasoning"] == 0.5
    assert applier.status(rid) == REC_STATUS_ROLLED_BACK


def test_rollback_without_apply_fails() -> None:
    applier = ConfigApplier()
    rid = applier.propose(_rec())
    applier.approve(rid)
    target = {"policy": {"ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}}}}
    assert applier.rollback(rid, target) is False


def test_history_recorded() -> None:
    applier = ConfigApplier()
    rid = applier.propose(_rec())
    applier.approve(rid)
    target = {"policy": {"ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}}}}
    applier.apply(rid, target)
    hist = applier.history()
    assert len(hist) == 1
    assert hist[0]["previous_value"] == 0.5
    assert hist[0]["new_value"] == 0.7
    assert hist[0]["approved_by"] == "human"


def test_apply_unknown_rec_fails() -> None:
    applier = ConfigApplier()
    target = {}
    assert applier.apply("nope", target) is False
