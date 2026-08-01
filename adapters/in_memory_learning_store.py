"""(adapters) InMemoryLearningStore — ILearningStore wrapper over IMemoryStore
(Wave 12, ADR-015 Phase B-C).

LAW 6: do NOT spin up a new storage engine. `ExecutionTrace` is stored as a
`MemoryItem` inside an existing `IMemoryStore` (Wave 9, `InMemoryMemoryStore`),
tagged `MemoryKind.LEARNING`. This adapter is pure *semantics* — grouping,
aggregation, trends — over generic memory. The storage contract stays owned by
Wave 9.

Serialization note (ADR-015 §Consequences): `ExecutionTrace` holds nested frozen
dataclasses (`Tuple[StepTrace, ...]`), which `json.dumps(obj.__dict__)` cannot
handle. We use `dataclasses.asdict` for the round trip and rebuild the entities
explicitly.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from typing import Dict, List, Optional

from contracts.i_learning import (
    ExecutionTrace,
    ILearningStore,
    Pattern,
    StepTrace,
)
from contracts.i_memory import IMemoryStore, MemoryItem, MemoryKind, MemoryQuery


# metric -> how to pull a float from a StepTrace / ExecutionTrace
_METRIC_STEP = {
    "avg_latency": "latency_ms",
    "avg_cost": "cost",
    "avg_eval_score": "eval_score",
}
_GROUP_KEYS = {"model_id", "provider", "task_type"}


class InMemoryLearningStore(ILearningStore):
    """Thin analysis layer over an injected IMemoryStore (Wave 9)."""

    def __init__(self, store: IMemoryStore) -> None:
        # LAW 3: explicit injected state, no globals
        self._store = store

    # --- ILearningStore ----------------------------------------------------
    def record(self, trace: ExecutionTrace) -> None:
        key = f"learning:{trace.trace_id}"
        # asdict flattens nested dataclasses to dicts (lossless for our shape)
        payload = asdict(trace)
        item = MemoryItem(
            key=key,
            content=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            timestamp=trace.timestamp or time.time(),
            importance=0.7,
            tags=(MemoryKind.LEARNING,),
            source="agent_platform",
        )
        self._store.put(item)

    def query(self, pattern: str, limit: int = 10) -> List[ExecutionTrace]:
        items = self._store.query(
            MemoryQuery(tags=[MemoryKind.LEARNING], limit=limit if limit and limit > 0 else None)
        )
        needle = (pattern or "").lower()
        out: List[ExecutionTrace] = []
        for it in items:
            trace = self._decode(it.content)
            if needle and needle not in (trace.goal + " " + trace.final_status).lower():
                continue
            out.append(trace)
        # newest first; MemoryItem query already sorts, but stay defensive
        out.sort(key=lambda t: t.timestamp, reverse=True)
        return out[:limit] if limit and limit >= 0 else out

    def aggregate(self, metric: str, group_by: str) -> Dict[str, float]:
        if metric not in ("avg_latency", "avg_cost", "success_rate", "avg_eval_score"):
            raise ValueError(f"unknown metric: {metric}")
        if group_by not in _GROUP_KEYS:
            raise ValueError(f"unknown group_by: {group_by}")

        traces = self.query("", limit=-1)
        acc: Dict[str, List[float]] = {}

        for t in traces:
            gkey = self._group_key(t, group_by)
            if gkey is None:
                continue
            val = self._metric_value(t, metric)
            if val is None:
                continue
            acc.setdefault(gkey, []).append(val)

        return {k: sum(v) / len(v) for k, v in acc.items()}

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _decode(content: str) -> ExecutionTrace:
        d = json.loads(content)
        steps = tuple(StepTrace(**s) for s in d.get("steps", ()))
        return ExecutionTrace(**{**d, "steps": steps})

    @staticmethod
    def _group_key(trace: ExecutionTrace, group_by: str) -> Optional[str]:
        if group_by == "model_id":
            ids = {s.model_id for s in trace.steps if s.model_id}
            return "+".join(sorted(ids)) if ids else None
        if group_by == "provider":
            # provider = first token before ':' or '/' in model_id
            provs = {
                s.model_id.split(":")[0].split("/")[0]
                for s in trace.steps
                if s.model_id
            }
            return "+".join(sorted(provs)) if provs else None
        if group_by == "task_type":
            # heuristic category from goal keywords (mirrors PatternExtractor)
            g = trace.goal.lower()
            if "reasoning" in g:
                return "reasoning"
            if "code" in g or "generate" in g or "summar" in g:
                return "generation"
            return "general"
        return None

    @staticmethod
    def _metric_value(trace: ExecutionTrace, metric: str) -> Optional[float]:
        if metric == "success_rate":
            if not trace.steps:
                return None
            ok = sum(1 for s in trace.steps if trace.final_status == "done")
            return ok / len(trace.steps)
        # step-level aggregate across the trace's steps
        field = _METRIC_STEP.get(metric)
        if not field or not trace.steps:
            return None
        vals = [getattr(s, field) for s in trace.steps if getattr(s, field, 0.0) > 0]
        return sum(vals) / len(vals) if vals else 0.0
