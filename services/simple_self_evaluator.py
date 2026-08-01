"""(services) SimpleSelfEvaluator — ISelfEvaluator (Wave 14, ADR-017).

Retrospective analysis over Wave 12 `ExecutionTrace`s. Computes three metrics
STRICTLY from real fields (ADR-017 §Корректировки):
- plan_success_rate: fraction of traces with final_status == "done"
- pattern_drift: applied / (applied + rolled_back) from caller-supplied rec statuses
- optimization_yield: fraction of proposed recs that reached approved+

Pure analysis — produces a frozen `EvaluationReport`, mutates nothing (LAW 3/4).

LAW 2: imports only contracts.* + stdlib. The evaluator does NOT import the
concrete ConfigApplier; instead it receives `rec_statuses` (a snapshot of
recommendation statuses) from the caller, keeping the service decoupled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from contracts.i_learning import ExecutionTrace, Pattern
from contracts.i_autonomy import EvaluationReport, ISelfEvaluator

# statuses considered "shipped" toward optimization yield
_SHIPPED = ("approved", "applied")


class SimpleSelfEvaluator(ISelfEvaluator):
    """Compute success/drift/yield from history (v0.1)."""

    def __init__(self, drift_attention_threshold: float = 0.5) -> None:
        # drift above this fraction flags rec ids for human attention
        self._drift_attention = drift_attention_threshold

    def evaluate(
        self,
        traces: List[ExecutionTrace],
        patterns: List[Pattern],
        rec_statuses: Dict[str, str] = None,
    ) -> EvaluationReport:
        rec_statuses = rec_statuses or {}
        total = len(traces)
        done = sum(1 for t in traces if t.final_status == "done")
        plan_success_rate = (done / total) if total else 0.0

        # pattern_drift from recommendation statuses (applied vs rolled_back)
        applied = sum(1 for s in rec_statuses.values() if s == "applied")
        rolled = sum(1 for s in rec_statuses.values() if s == "rolled_back")
        denom = applied + rolled
        pattern_drift = (applied / denom) if denom else 0.0

        # optimization_yield: proposed recs that reached approved+
        prop = len(rec_statuses)
        shipped = sum(1 for s in rec_statuses.values() if s in _SHIPPED)
        optimization_yield = (shipped / prop) if prop else 0.0

        attention = tuple(
            rid for rid, s in rec_statuses.items()
            if s == "rolled_back" or (s == "applied" and pattern_drift < self._drift_attention)
        )

        return EvaluationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            plan_success_rate=plan_success_rate,
            pattern_drift=pattern_drift,
            optimization_yield=optimization_yield,
            attention=attention,
            trace_ids=tuple(t.trace_id for t in traces),
        )
