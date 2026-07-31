"""(services) LlmOptimizer — adapter of IOptimizer (Wave 14, ADR-017 §2.4).

The SECOND IOptimizer (alongside Wave 13's PatternBasedOptimizer). Uses an LLM
to generate Recommendations from Patterns, but is bound by the SAME constraints:
- confidence gate MIN_CONFIDENCE = 0.7 (LAW 5)
- target whitelist: only "policy:" / "knowledge:" paths
- value is JSON-serialised scalar/dict, never executable code
Every rec still flows through IGuardrail before ConfigApplier (enforced by the
caller — this adapter only proposes).

v0.1: if no `llm_fn` is supplied, delegates to `PatternBasedOptimizer` as a
deterministic fallback so the adapter is testable without a live LLM.

LAW 2: imports only contracts.* + stdlib + the sibling concrete optimizer
(which itself imports only contracts.* — no domain->adapter violation, since an
*adapter* implementing a port is allowed to know its fallback).
"""
from __future__ import annotations

import json
import uuid
from typing import Callable, Dict, List, Optional

from contracts.i_learning import Pattern
from contracts.i_optimization import (
    REC_STATUS_PROPOSED,
    IOptimizer,
    Recommendation,
)
from services.pattern_based_optimizer import PatternBasedOptimizer


MIN_CONFIDENCE = 0.7
ALLOWED_PREFIXES = ("policy:", "knowledge:")


# An LLM call shape: given a prompt string, return either a JSON Recommendation
# dict or a natural-language answer the adapter parses.
LlmFn = Callable[[str], str]


class LlmOptimizer(IOptimizer):
    """LLM-backed optimizer; falls back to rule-based when no llm_fn given."""

    def __init__(
        self,
        llm_fn: Optional[LlmFn] = None,
        fallback: Optional[IOptimizer] = None,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        self._llm_fn = llm_fn
        self._fallback = fallback or PatternBasedOptimizer()
        self._min_confidence = min_confidence

    def recommend(
        self, patterns: List[Pattern], current_config: Dict
    ) -> List[Recommendation]:
        if self._llm_fn is None:
            # deterministic fallback path (v0.1, no live LLM)
            return self._fallback.recommend(patterns, current_config)

        recs: List[Recommendation] = []
        for p in patterns:
            if p.confidence <= self._min_confidence:
                continue
            raw = self._llm_fn(self._prompt(p, current_config))
            rec = self._parse(p, raw)
            if rec is not None and self._target_allowed(rec.target):
                recs.append(rec)
        return recs

    # --- internals -------------------------------------------------------
    def _prompt(self, pattern: Pattern, config: Dict) -> str:
        return (
            "Generate a config Recommendation for this learning pattern.\n"
            f"Pattern: {pattern.description}\n"
            f"Confidence: {pattern.confidence}\n"
            f"Applies to: {list(pattern.applies_to)}\n"
            f"Current config (excerpt): {json.dumps(config, ensure_ascii=False)[:500]}\n"
            "Respond with JSON: "
            '{"target": "policy:...", "value": <json-serialisable scalar or dict>, '
            '"rationale": "..."}'
        )

    def _parse(self, pattern: Pattern, raw: str) -> "Optional[Recommendation]":
        try:
            # strip code fences if the LLM wrapped the JSON
            text = raw.strip().strip("`").lstrip("json").strip()
            data = json.loads(text)
            target = str(data.get("target", ""))
            value = json.dumps(data.get("value"), ensure_ascii=False, sort_keys=True)
            rationale = str(data.get("rationale", pattern.recommendation))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if not self._target_allowed(target):
            return None
        return Recommendation(
            id=f"rec:llm:{uuid.uuid4().hex[:12]}",
            target=target,
            value=value,
            rationale=rationale,
            confidence=pattern.confidence,
            source_pattern=pattern.description,
            status=REC_STATUS_PROPOSED,
        )

    @staticmethod
    def _target_allowed(target: str) -> bool:
        return any(target.startswith(p) for p in ALLOWED_PREFIXES)
