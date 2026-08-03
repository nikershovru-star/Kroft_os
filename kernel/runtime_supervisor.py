"""Runtime Supervisor — adaptive runtime loop (ТЗ-RT-01, ADR-062).

K1-compliant: stdlib + contracts only (reference impls live in this kernel/ module).

The supervisor runs the Round-2 adaptive loop:
    collect operational metrics -> reflect (detect patterns) -> apply tuning
under the O1 Self-Evolving guard. It tunes ONLY SOFT runtime parameters
(timeouts, thresholds, budgets) of the registered targets. FSM invariants,
HARD policies, contracts and kernel structure are NEVER touched.

Separation from RF-01 (cognitive reflection):
- RF-01 evolves SOFT *content* (semantic facts, soft policies) from cognitive
  experience. RuntimeSupervisor does NOT write semantic/policy content.
- RuntimeSupervisor tunes *operational parameters* from operational metrics.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    NodeLamportClock,
    ProvenanceType,
)
from contracts.i_runtime_reflection import (
    IRuntimeMetrics,
    IRuntimeReflection,
    ITuningApplier,
    RuntimeMetric,
    TuningProposal,
)


class RuntimeSupervisor:
    """Drives the collect -> reflect -> apply loop for SOFT runtime tuning (O1)."""

    def __init__(self,
                 metrics: IRuntimeMetrics,
                 reflection: IRuntimeReflection,
                 applier: ITuningApplier,
                 targets: Optional[Dict[str, object]] = None,
                 clock: Optional[NodeLamportClock] = None) -> None:
        self._metrics = metrics
        self._reflection = reflection
        self._applier = applier
        self._clock = clock if clock is not None else NodeLamportClock("supervisor")
        # register tunable targets into the applier (O1 whitelist enforced there)
        for param, obj in (targets or {}).items():
            self._applier.register_target(param, obj)

    def step(self) -> List[TuningProposal]:
        """One adaptive cycle. Returns the proposals that were successfully applied.

        O1 guard is enforced inside `ITuningApplier.apply`: only SOFT, whitelisted,
        targeted proposals mutate anything; HARD/unknown proposals are rejected.
        """
        metrics = self._metrics.collect()
        proposals = self._reflection.reflect(metrics)
        applied: List[TuningProposal] = []
        for prop in proposals:
            if self._applier.apply(prop):
                applied.append(prop)
        return applied

    # alias used by some callers / tests
    def run_once(self) -> List[TuningProposal]:
        return self.step()


def build_runtime_metrics(
    memory_evolution=None,
    network_transport=None,
    resource_manager=None,
    delivery_success_rate: Optional[float] = None,
    memory_growth_rate: Optional[float] = None,
    consolidation_confidence: Optional[float] = None,
    clock: Optional[NodeLamportClock] = None,
) -> List[RuntimeMetric]:
    """Assemble the current operational metric snapshot from live targets.

    Reads the CURRENT values of the SOFT-tunable parameters (so reflection proposals
    carry honest old->new), plus optional operational signals (federation delivery
    rate, memory growth, consolidation confidence) fed by the runtime.
    """
    clk = clock if clock is not None else NodeLamportClock("metrics")
    mark = clk.tick()
    cs = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
    out: List[RuntimeMetric] = []

    # current tunable values
    if network_transport is not None and hasattr(network_transport, "_connect_timeout"):
        out.append(RuntimeMetric("network.ensure_connected_timeout.current",
                                 float(network_transport._connect_timeout), cs, mark))
    if memory_evolution is not None:
        if hasattr(memory_evolution, "_min_rep"):
            out.append(RuntimeMetric("memory.min_repetitions.current",
                                     float(memory_evolution._min_rep), cs, mark))
        if hasattr(memory_evolution, "_thr"):
            out.append(RuntimeMetric("memory.confidence_threshold.current",
                                     float(memory_evolution._thr), cs, mark))
    if resource_manager is not None and hasattr(resource_manager, "_budgets"):
        out.append(RuntimeMetric("resource.budgets.tokens.current",
                                 float(resource_manager._budgets.get("tokens", 0)), cs, mark))

    # operational signals (driven by the live runtime; None => not observed yet)
    if delivery_success_rate is not None:
        out.append(RuntimeMetric("federation.delivery_success_rate",
                                 float(delivery_success_rate), cs, mark))
    if memory_growth_rate is not None:
        out.append(RuntimeMetric("memory.growth_rate_per_tick",
                                 float(memory_growth_rate), cs, mark))
    if consolidation_confidence is not None:
        out.append(RuntimeMetric("memory.consolidation_confidence",
                                 float(consolidation_confidence), cs, mark))
    return out
