"""Runtime / System Reflection — LLM-FREE reference implementation (ТЗ-RT-01, ADR-062).

K1-compliant: imports ONLY contracts + stdlib. No services/adapter/runtime imports.

Round 2 adaptive runtime: the system observes its OPERATIONAL metrics (delivery rates,
memory growth, connect latency) — NOT cognitive experience — reflects on them, and
adaptively tunes SOFT runtime parameters under the O1 Self-Evolving guard.

Separation from RF-01 (cognitive reflection):
- RF-01 reflects on cognitive experience -> evolves SOFT *content* (semantic facts,
  soft policies). It NEVER tunes operational parameters.
- RT-01 (this module) reflects on operational metrics -> proposes TUNING of SOFT
  *runtime parameters* (timeouts, thresholds, budgets). It NEVER writes semantic
  content (that is RF-01 + ME-01).

O1 guard: tuning is SOFT-only. FSM invariants, HARD policies, contracts and kernel
structure are IMMUTABLE. `ReferenceTuningApplier.apply` rejects any proposal whose
`layer` is not SOFT or whose `param` is not in the allowed SOFT set.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    NodeLamportClock,
    Provenance,
    ProvenanceType,
)
from contracts.i_runtime_reflection import (
    IRuntimeMetrics,
    IRuntimeReflection,
    ITuningApplier,
    RuntimeMetric,
    TuningLayer,
    TuningProposal,
)

# Tunable SOFT parameter keys and their target attribute names on the injected objects.
# (param_key -> attribute name used by ReferenceTuningApplier.apply via setattr.)
_PARAM_ATTR: Dict[str, str] = {
    "network.ensure_connected_timeout": "_connect_timeout",
    "memory.min_repetitions": "_min_rep",
    "memory.confidence_threshold": "_thr",
    "resource.budgets.tokens": "_budgets",  # dict: applier sets budgets["tokens"]
}

# Allowed SOFT parameter keys (whitelist — O1 guard surface).
ALLOWED_SOFT_PARAMS: Set[str] = set(_PARAM_ATTR.keys())


class ReferenceRuntimeMetrics(IRuntimeMetrics):
    """Collects operational runtime metrics.

    LLM-free core: holds an injectable snapshot (for tests + supervisor wiring) and
    can be extended to pull live counters from federation / memory / resource manager.
    The deterministic reflection rules operate on whatever `collect()` returns.
    """

    def __init__(self, snapshot: Optional[List[RuntimeMetric]] = None,
                 clock: Optional[NodeLamportClock] = None) -> None:
        self._clock = clock if clock is not None else NodeLamportClock("runtime")
        self._snapshot: List[RuntimeMetric] = list(snapshot or [])

    def set_snapshot(self, metrics: List[RuntimeMetric]) -> None:
        self._snapshot = list(metrics)

    def collect(self) -> List[RuntimeMetric]:
        return list(self._snapshot)


class ReferenceRuntimeReflection(IRuntimeReflection):
    """Deterministic runtime reflection (LLM-free).

    Each rule maps a detected operational pattern to a single, reproducible SOFT
    tuning proposal. Rules are monotonic and bounded (raise/lower within caps) so the
    loop is stable (no oscillation): raising a timeout makes delivery succeed, which
    then stops triggering the raise rule.
    """

    def __init__(self, clock: Optional[NodeLamportClock] = None) -> None:
        self._clock = clock if clock is not None else NodeLamportClock("runtime")

    def reflect(self, metrics: List[RuntimeMetric]) -> List[TuningProposal]:
        by_name: Dict[str, RuntimeMetric] = {m.name: m for m in metrics}
        proposals: List[TuningProposal] = []
        mark = self._clock.tick()  # advance the shared runtime clock per reflection

        # Rule R1: low federation delivery success rate -> raise connect timeout.
        # Old value is read from the dedicated current-value metric so the proposal
        # is honest (old -> new), not a placeholder.
        if ("federation.delivery_success_rate" in by_name
                and "network.ensure_connected_timeout.current" in by_name):
            rate = by_name["federation.delivery_success_rate"]
            cur = by_name["network.ensure_connected_timeout.current"]
            if rate.value < 0.8:
                new = min(10.0, max(1.0, cur.value * 1.5))
                if new != cur.value:
                    proposals.append(self._proposal(
                        param="network.ensure_connected_timeout",
                        old_value=cur.value, new_value=new,
                        rationale=f"low delivery rate {rate.value:.2f} -> raise connect timeout "
                                  f"{cur.value:.2f}->{new:.2f}",
                        conf=rate.confidence, mark=mark))

        # Rule R2: fast memory growth -> raise min_repetitions (consolidate less often).
        if ("memory.growth_rate_per_tick" in by_name
                and "memory.min_repetitions.current" in by_name):
            growth = by_name["memory.growth_rate_per_tick"]
            cur = by_name["memory.min_repetitions.current"]
            if growth.value > 0.5:
                new = min(10.0, cur.value + 1.0)
                if new != cur.value:
                    proposals.append(self._proposal(
                        param="memory.min_repetitions",
                        old_value=cur.value, new_value=new,
                        rationale=f"fast memory growth {growth.value:.2f}/tick -> raise "
                                  f"min_repetitions {cur.value:.0f}->{new:.0f}",
                        conf=growth.confidence, mark=mark))

        # Rule R3: low consolidation confidence -> raise confidence_threshold.
        if ("memory.consolidation_confidence" in by_name
                and "memory.confidence_threshold.current" in by_name):
            conf = by_name["memory.consolidation_confidence"]
            cur = by_name["memory.confidence_threshold.current"]
            if conf.value < 0.6:
                new = min(0.95, cur.value + 0.1)
                if new != cur.value:
                    proposals.append(self._proposal(
                        param="memory.confidence_threshold",
                        old_value=cur.value, new_value=new,
                        rationale=f"low consolidation confidence {conf.value:.2f} -> raise "
                                  f"threshold {cur.value:.2f}->{new:.2f}",
                        conf=conf.confidence, mark=mark))

        return proposals

    def _proposal(self, param: str, old_value: float, new_value: float,
                  rationale: str, conf: ConfidenceScore, mark: CausalMark) -> TuningProposal:
        return TuningProposal(
            param=param, old_value=old_value, new_value=new_value,
            rationale=rationale, confidence=conf, causal=mark,
            layer=TuningLayer.SOFT)


class ReferenceTuningApplier(ITuningApplier):
    """Applies SOFT tuning proposals under the O1 Self-Evolving guard.

    `targets` maps a SOFT param key -> the object that owns the tunable attribute
    (e.g. {"memory.min_repetitions": reference_memory_evolution}). `apply` rejects any
    proposal that is not SOFT or whose param is not whitelisted / has no target.
    """

    def __init__(self, targets: Optional[Dict[str, object]] = None,
                 allowed: Optional[Set[str]] = None) -> None:
        self._targets: Dict[str, object] = dict(targets or {})
        self._allowed: Set[str] = set(allowed if allowed is not None else ALLOWED_SOFT_PARAMS)

    def register_target(self, param: str, obj: object) -> None:
        self._targets[param] = obj

    def allowed_params(self) -> Set[str]:
        return set(self._allowed)

    def apply(self, proposal: TuningProposal) -> bool:
        # O1 guard: SOFT-only, whitelisted, has a target.
        if proposal.layer != TuningLayer.SOFT:
            return False
        if proposal.param not in self._allowed:
            return False
        obj = self._targets.get(proposal.param)
        if obj is None:
            return False
        attr = _PARAM_ATTR.get(proposal.param)
        if attr is None:
            return False
        # Apply. For dict-valued budgets, set the specific key; otherwise setattr.
        if proposal.param == "resource.budgets.tokens" and isinstance(obj, dict):
            obj[proposal.param.split(".")[2]] = proposal.new_value
        else:
            setattr(obj, attr, proposal.new_value)
        return True
