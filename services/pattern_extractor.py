"""(services) RuleBasedPatternExtractor — IPatternExtractor (Wave 12, ADR-015 Phase D).

v0.1 is rule-based aggregation (ADR-015 §Decision): group traces by goal
category, compare avg_eval_score per model_id, emit a Pattern when one model is
consistently better by > 0.1. No LLM — that belongs to Wave 13/14.

LAW 4: every Pattern carries `confidence` (scaled by margin AND sample size) and
`applies_to` (the goal category + the winning model's provider tag).
LAW 5: patterns are derived from measured numbers, never guesses.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from contracts.i_learning import ExecutionTrace, IPatternExtractor, Pattern


# goal keyword -> category (mirrors InMemoryLearningStore._group_key task_type)
_CATEGORY_KEYWORDS = {
    "reasoning": ("reasoning",),
    "generation": ("code", "generate", "summar", "write", "translate"),
    "general": (),
}


def _categorize(goal: str) -> str:
    g = goal.lower()
    if "reasoning" in g:
        return "reasoning"
    if any(k in g for k in ("code", "generate", "summar", "write", "translate")):
        return "generation"
    return "general"


class RuleBasedPatternExtractor(IPatternExtractor):
    """Aggregate traces, compare models per category, emit recommendations."""

    # margin at which a model is declared "better"
    MARGIN = 0.1
    # minimum samples per model before a pattern is trusted
    MIN_SAMPLES = 3

    def extract(self, traces: List[ExecutionTrace]) -> List[Pattern]:
        if not traces:
            return []

        # category -> model_id -> list of eval scores
        buckets: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for t in traces:
            cat = _categorize(t.goal)
            for s in t.steps:
                if s.model_id and s.eval_score > 0:
                    buckets[cat][s.model_id].append(s.eval_score)

        patterns: List[Pattern] = []
        for cat, models in buckets.items():
            scored = {
                m: (sum(v) / len(v), len(v))
                for m, v in models.items()
                if len(v) >= self.MIN_SAMPLES
            }
            if len(scored) < 2:
                continue
            best = max(scored.items(), key=lambda kv: kv[1][0])
            rest = [kv for kv in scored.items() if kv[0] != best[0]]
            for other in rest:
                margin = best[1][0] - other[1][0]
                if margin >= self.MARGIN:
                    conf = self._confidence(margin, best[1][1], other[1][1])
                    prov_best = best[0].split(":")[0].split("/")[0]
                    patterns.append(
                        Pattern(
                            description=(
                                f"In '{cat}' tasks, {best[0]} scores "
                                f"{best[1][0]:.2f} vs {other[0]} {other[1][1]:.2f} "
                                f"avg eval over {best[1][1] + other[1][1]} runs."
                            ),
                            confidence=round(conf, 2),
                            applies_to=(cat, prov_best),
                            recommendation=(
                                f"Prefer {best[0]} for {cat} tasks "
                                f"(+{margin:.2f} avg eval over {other[0]})."
                            ),
                        )
                    )
        return patterns

    @staticmethod
    def _confidence(margin: float, n_best: int, n_other: int) -> float:
        # scale by margin (0.1 -> 0.35, 0.3+ -> ~0.9) and sample size
        base = min(1.0, 0.35 + (margin - 0.1) * 2.0)
        sample = min(1.0, (n_best + n_other) / 20.0)
        return max(0.2, min(0.95, base * (0.6 + 0.4 * sample)))
