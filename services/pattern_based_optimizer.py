"""(services) PatternBasedOptimizer — IOptimizer (Wave 13, ADR-016 Phase C).

Turns Wave 12 `Pattern`s into `Recommendation`s. v0.1 is rule-based:
only emits a rec when `pattern.confidence > 0.7` (LAW 5 — measured, not guessed).
No LLM, no apply — that is Wave 14 / ConfigApplier's job.

LAW 2: imports only contracts.* (Pattern from i_learning, ports from i_optimization).
LAW 3: produces frozen Recommendation entities; keeps no hidden mutable state.
LAW 4: every rec carries source_pattern + rationale (attributable evidence).
"""
from __future__ import annotations

import json
import uuid
from typing import Dict, List

from contracts.i_learning import Pattern
from contracts.i_optimization import (
    IOptimizer,
    REC_STATUS_PROPOSED,
    Recommendation,
)


# Minimum confidence before we even propose a change (LAW 5 gate)
MIN_CONFIDENCE = 0.7


class PatternBasedOptimizer(IOptimizer):
    """Generate config Recommendations from Learning Patterns."""

    def recommend(
        self, patterns: List[Pattern], current_config: Dict
    ) -> List[Recommendation]:
        recs: List[Recommendation] = []
        for p in patterns:
            if p.confidence <= MIN_CONFIDENCE:
                continue
            rec = self._build(p, current_config)
            if rec is not None:
                recs.append(rec)
        return recs

    # --- rule-based rec builders -----------------------------------------
    def _build(self, p: Pattern, cfg: Dict) -> "Recommendation | None":
        applies = p.applies_to
        cat = applies[0] if applies else "general"
        prov = applies[1] if len(applies) > 1 else (cat if cat != "general" else "default")

        # Rule 1: a model clearly beats others on a category -> raise its weight
        if "better" in p.recommendation.lower() or "prefer" in p.recommendation.lower():
            target = f"policy:ProviderSelectionPolicy:weights:{cat}"
            cur = cfg.get("policy", {}).get("ProviderSelectionPolicy", {}).get("weights", {}).get(cat, 0.5)
            new_w = min(1.0, round(cur + 0.2, 2))
            return self._rec(
                p, target, new_w,
                f"Pattern confidence {p.confidence:.2f}: {p.recommendation}. "
                f"Raise '{cat}' weight {cur} -> {new_w}.",
            )

        # Rule 2: a model is consistently weak -> block it in SecurityPolicy
        if "block" in p.recommendation.lower() or "avoid" in p.recommendation.lower():
            target = "policy:SecurityPolicy:blocked_models"
            blocked = list(cfg.get("policy", {}).get("SecurityPolicy", {}).get("blocked_models", []))
            model = prov
            if model and model not in blocked:
                return self._rec(
                    p, target, {"add": model},
                    f"Pattern confidence {p.confidence:.2f}: {p.recommendation}. "
                    f"Add '{model}' to blocked_models.",
                )

        # Rule 3: too many facts dropped -> relax KnowledgePlatform threshold
        if "min_confidence" in p.recommendation.lower() or "threshold" in p.recommendation.lower():
            target = "knowledge:KnowledgePlatform:min_confidence"
            cur = cfg.get("knowledge", {}).get("KnowledgePlatform", {}).get("min_confidence", 0.7)
            new_t = max(0.0, round(cur - 0.1, 2))
            return self._rec(
                p, target, {"value": new_t},
                f"Pattern confidence {p.confidence:.2f}: {p.recommendation}. "
                f"Lower min_confidence {cur} -> {new_t}.",
            )

        # default: still surface the pattern as an observation rec
        return self._rec(
            p, f"observe:{cat}:{prov}", {"note": p.recommendation},
            f"Pattern confidence {p.confidence:.2f}: {p.recommendation}.",
        )

    def _rec(self, p: Pattern, target: str, value: dict, rationale: str) -> Recommendation:
        return Recommendation(
            id=f"rec:{uuid.uuid4().hex[:12]}",
            target=target,
            value=json.dumps(value, ensure_ascii=False, sort_keys=True),
            rationale=rationale,
            confidence=p.confidence,
            source_pattern=p.description,  # Pattern has no id (ADR-016 §Отклонения)
            status=REC_STATUS_PROPOSED,
        )
