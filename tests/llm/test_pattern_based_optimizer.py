"""services/test_pattern_based_optimizer.py — pattern -> recommendation (Wave 13).

Verifies LAW 5 (only confident patterns produce recs) and LAW 4 (source_pattern).
"""
from __future__ import annotations

from contracts.i_learning import Pattern
from contracts.i_optimization import REC_STATUS_PROPOSED, Recommendation
from services.pattern_based_optimizer import PatternBasedOptimizer


def _p(desc, conf, applies, rec):
    return Pattern(description=desc, confidence=conf, applies_to=applies, recommendation=rec)


BASE_CFG = {
    "policy": {
        "ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}},
        "SecurityPolicy": {"blocked_models": []},
    },
    "knowledge": {"KnowledgePlatform": {"min_confidence": 0.7}},
}


def test_no_rec_when_confidence_low() -> None:
    opt = PatternBasedOptimizer()
    pats = [_p("phi4 beats gpt", 0.6, ("reasoning", "phi4"), "Prefer phi4 for reasoning tasks")]
    assert opt.recommend(pats, BASE_CFG) == []


def test_rec_when_confidence_high_raises_weight() -> None:
    opt = PatternBasedOptimizer()
    pats = [_p("phi4 beats gpt", 0.92, ("reasoning", "phi4"), "Prefer phi4 for reasoning tasks")]
    recs = opt.recommend(pats, BASE_CFG)
    assert len(recs) == 1
    r = recs[0]
    assert r.status == REC_STATUS_PROPOSED
    assert "ProviderSelectionPolicy:weights:reasoning" in r.target
    assert r.confidence == 0.92
    assert r.source_pattern == "phi4 beats gpt"


def test_rec_blocks_weak_model() -> None:
    opt = PatternBasedOptimizer()
    pats = [_p("felo-chat is weak", 0.85, ("generation", "felo-chat"), "Avoid felo-chat for generation")]
    recs = opt.recommend(pats, BASE_CFG)
    assert any("SecurityPolicy:blocked_models" in r.target for r in recs)
    assert any("felo-chat" in r.value for r in recs)


def test_rec_lowers_knowledge_threshold() -> None:
    opt = PatternBasedOptimizer()
    pats = [_p("too strict", 0.88, ("general",), "Lower min_confidence in KnowledgePlatform from 0.7 to 0.6")]
    recs = opt.recommend(pats, BASE_CFG)
    assert any("KnowledgePlatform:min_confidence" in r.target for r in recs)


def test_multiple_patterns_multiple_recs() -> None:
    opt = PatternBasedOptimizer()
    pats = [
        _p("phi4 beats gpt", 0.9, ("reasoning", "phi4"), "Prefer phi4 for reasoning tasks"),
        _p("felo weak", 0.8, ("generation", "felo"), "Avoid felo for generation"),
    ]
    recs = opt.recommend(pats, BASE_CFG)
    assert len(recs) == 2


def test_rec_value_is_serialised_scalar() -> None:
    import json
    opt = PatternBasedOptimizer()
    pats = [_p("phi4 beats gpt", 0.92, ("reasoning", "phi4"), "Prefer phi4 for reasoning tasks")]
    r = opt.recommend(pats, BASE_CFG)[0]
    val = json.loads(r.value)
    assert isinstance(val, (int, float))
    assert val > 0.5
