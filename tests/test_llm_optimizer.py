"""services/test_llm_optimizer.py — LLM-backed IOptimizer adapter (Wave 14).

Verifies LAW 5 (confidence gate), target whitelist, and the deterministic
fallback when no llm_fn is supplied (v0.1, no live LLM needed for tests).
"""
from __future__ import annotations

import json

from contracts.i_learning import Pattern
from services.llm_optimizer import LlmOptimizer


BASE_CFG = {"policy": {"ProviderSelectionPolicy": {"weights": {"reasoning": 0.5}}}}


def test_fallback_when_no_llm_fn() -> None:
    opt = LlmOptimizer(llm_fn=None)  # fallback = PatternBasedOptimizer
    pats = [Pattern("phi4 beats gpt", 0.92, ("reasoning", "phi4"), "Prefer phi4 for reasoning tasks")]
    recs = opt.recommend(pats, BASE_CFG)
    assert len(recs) == 1
    assert recs[0].confidence == 0.92


def test_llm_fn_used_when_supplied() -> None:
    def fake_llm(prompt: str) -> str:
        return json.dumps({"target": "policy:ProviderSelectionPolicy:weights:reasoning",
                            "value": 0.7, "rationale": "llm says raise"})
    opt = LlmOptimizer(llm_fn=fake_llm)
    pats = [Pattern("phi4 beats gpt", 0.91, ("reasoning", "phi4"), "Prefer phi4")]
    recs = opt.recommend(pats, BASE_CFG)
    assert len(recs) == 1
    assert json.loads(recs[0].value) == 0.7
    assert recs[0].source_pattern == "phi4 beats gpt"


def test_confidence_gate_blocks_low() -> None:
    opt = LlmOptimizer(llm_fn=None)
    pats = [Pattern("weak", 0.5, ("reasoning",), "Prefer")]
    assert opt.recommend(pats, BASE_CFG) == []


def test_target_whitelist_enforced() -> None:
    # LLM returns a forbidden target (e.g. "secret:...") -> rec dropped
    def evil_llm(prompt: str) -> str:
        return json.dumps({"target": "secret:something", "value": 1, "rationale": "x"})
    opt = LlmOptimizer(llm_fn=evil_llm)
    pats = [Pattern("p", 0.9, ("reasoning",), "Prefer")]
    assert opt.recommend(pats, BASE_CFG) == []


def test_malformed_llm_output_dropped() -> None:
    def bad_llm(prompt: str) -> str:
        return "not json at all"
    opt = LlmOptimizer(llm_fn=bad_llm)
    pats = [Pattern("p", 0.9, ("reasoning",), "Prefer")]
    assert opt.recommend(pats, BASE_CFG) == []
