"""Value system reference implementations (ТЗ-SE-01 extraction from cognitive_kernel).

K1-compliant: stdlib + contracts only. Split out of cognitive_kernel.py so that
kernel/self_evolution.py can import SimpleValueSystem WITHOUT creating a circular
import (cognitive_kernel imports self_evolution for build_kernel wiring).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from contracts.cognitive_domain import ConfidenceScore
from contracts.i_cognitive_kernel import IValueSystem


class SimpleValueSystem(IValueSystem):
    """Two-layer (I-11/I-19): hard veto from a set of violated-constraint checkers."""

    def __init__(self, hard_checkers: Optional[List[Callable[[object], Optional[str]]]] = None,
                 weights: Optional[Dict[str, float]] = None) -> None:
        self._hard = hard_checkers or []
        self._weights = weights or {"confidence": 1.0, "cost": -0.2, "risk": -0.5}

    def hard_violations(self, candidate: object) -> List[str]:
        out = []
        for chk in self._hard:
            v = chk(candidate)
            if v:
                out.append(v)
        return out

    def score(self, candidate: object) -> float:
        # soft utility: weighted sum of attributes (confidence/cost/risk)
        c = getattr(candidate, "confidence", None)
        base = c.value if isinstance(c, ConfidenceScore) else 0.5
        return base * self._weights.get("confidence", 1.0)
