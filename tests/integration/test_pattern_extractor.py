"""services/test_pattern_extractor.py — rule-based extraction (Wave 12).

Verifies LAW 4 (confidence + applies_to) and LAW 5 (numbers, not guesses).
"""
from __future__ import annotations

from contracts.i_learning import ExecutionTrace, Pattern, StepTrace
from services.pattern_extractor import RuleBasedPatternExtractor


def _trace(tid, goal, model, eval_score, n_steps=1):
    steps = tuple(
        StepTrace(
            step_id=f"s{i}", model_id=model, prompt=goal, output="o",
            eval_score=eval_score,
        )
        for i in range(n_steps)
    )
    return ExecutionTrace(trace_id=tid, goal=goal, workflow_id="w", steps=steps,
                          final_status="done", timestamp=1.0)


def test_empty_returns_no_patterns() -> None:
    assert RuleBasedPatternExtractor().extract([]) == []


def test_detects_better_model_for_reasoning() -> None:
    ex = RuleBasedPatternExtractor()
    traces = [
        _trace("a", "reasoning puzzle", "phi4", 0.91, n_steps=4),
        _trace("b", "reasoning puzzle", "phi4", 0.93, n_steps=4),
        _trace("c", "reasoning puzzle", "phi4", 0.90, n_steps=4),
        _trace("d", "reasoning puzzle", "gpt", 0.80, n_steps=4),
        _trace("e", "reasoning puzzle", "gpt", 0.82, n_steps=4),
        _trace("f", "reasoning puzzle", "gpt", 0.79, n_steps=4),
    ]
    patterns = ex.extract(traces)
    assert any(p.applies_to and p.applies_to[0] == "reasoning" for p in patterns)
    rec = [p for p in patterns if "phi4" in p.recommendation][0]
    assert rec.confidence > 0.0
    assert "reasoning" in rec.applies_to


def test_no_pattern_when_margin_small() -> None:
    ex = RuleBasedPatternExtractor()
    traces = [
        _trace("a", "reasoning puzzle", "phi4", 0.86, n_steps=4),
        _trace("b", "reasoning puzzle", "phi4", 0.85, n_steps=4),
        _trace("c", "reasoning puzzle", "gpt", 0.84, n_steps=4),
        _trace("d", "reasoning puzzle", "gpt", 0.83, n_steps=4),
    ]
    # margin < 0.1 => no pattern
    assert ex.extract(traces) == []


def test_min_samples_required() -> None:
    ex = RuleBasedPatternExtractor()
    # only 1 sample (n_steps=1) per model -> below MIN_SAMPLES
    traces = [
        _trace("a", "reasoning puzzle", "phi4", 0.95, n_steps=1),
        _trace("b", "reasoning puzzle", "gpt", 0.50, n_steps=1),
    ]
    assert ex.extract(traces) == []


def test_pattern_has_confidence_bounds() -> None:
    ex = RuleBasedPatternExtractor()
    traces = [
        _trace("a", "reasoning puzzle", "phi4", 0.95, n_steps=4),
        _trace("b", "reasoning puzzle", "phi4", 0.94, n_steps=4),
        _trace("c", "reasoning puzzle", "phi4", 0.96, n_steps=4),
        _trace("d", "reasoning puzzle", "gpt", 0.60, n_steps=4),
        _trace("e", "reasoning puzzle", "gpt", 0.62, n_steps=4),
        _trace("f", "reasoning puzzle", "gpt", 0.61, n_steps=4),
    ]
    patterns = ex.extract(traces)
    assert patterns
    for p in patterns:
        assert 0.0 <= p.confidence <= 1.0
        assert isinstance(p, Pattern)


def test_general_category_no_false_pattern() -> None:
    ex = RuleBasedPatternExtractor()
    traces = [
        _trace("a", "please do the thing", "phi4", 0.70, n_steps=4),
        _trace("b", "please do the thing", "gpt", 0.70, n_steps=4),
    ]
    assert ex.extract(traces) == []
