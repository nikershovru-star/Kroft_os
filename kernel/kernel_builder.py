"""KernelBuilder — extracted composition logic for the reference CognitiveKernel (ТЗ-OBS-01 Флаг 1).

The old ``build_kernel`` in ``kernel/cognitive_kernel.py`` had grown into a god-factory: each
new ТЗ appended an optional parameter (``llm_client``, ``live_metrics``, ``bus``) plus inline
``if ... is not None`` blocks and post-hoc ``attach_*`` calls. This module is the single
composition root for the reference kernel. ``build_kernel`` is now a thin, backward-compatible
wrapper that builds a ``KernelConfig`` from kwargs and delegates here.

Design (same invariants the old factory enforced):
- I-09: ONE shared Lamport clock per node, injected into world state AND reasoning/planner/
  world-model/reflection so all CausalMarks share causal order + node_origin == node_id.
- I-10 / kernel purity: LLM-free by construction. Optional ``llm_client`` is wrapped behind
  ILLMAdvisor (via ``adapter_for``); when None, advisor wrappers degrade to the pure reference
  path (no behavioural change vs. the LLM-free build).
- O1: Memory Evolution consolidates SOFT layer only; HARD immutable from experience.
- Флаг 2 / ТЗ-LLM-02: live collector wired into advisor wrappers so fallback bumps
  llm.fallback_rate; no-op if no collector.
- Флаг 3 (OBS-01): live metrics -> LiveRuntimeMetrics + RuntimeSupervisor adapting SOFT params;
  no-op without a collector.
- Federation / executor / soft-memory-sync are post-hoc ``attach_*`` calls (public API, still
  invoked here when the corresponding config field is present).

K1: imports only kernel + contracts (+ stdlib). K6 respected: builder wires kernel-internal
subsystems; it does NOT import runtime/adapters beyond the ILLMAdvisor port + adapter_for.
"""

from __future__ import annotations

from typing import Optional

from contracts.cognitive_domain import NodeLamportClock
from contracts.i_llm_advisor import ILLMAdvisor, adapter_for
from contracts.i_observability import ILiveMetricsCollector
from kernel.cognitive_kernel import (
    CognitiveKernel,
    SimpleAttention,
    SimpleResourceManager,
    DeterministicDecisionEngine,
    DeterministicExecutive,
    SimpleLearningPolicy,
    InMemoryWorldState,
)
from kernel.kernel_config import KernelConfig
from kernel.memory_store import InMemoryLayeredMemory
from kernel.memory_evolution import ReferenceMemoryEvolution
from kernel.reasoning import ReferenceReasoningEngine
from kernel.world_model import ReferenceWorldModel
from kernel.planning import ReferencePlanner
from kernel.reflection import ReferenceReflectionEngine
from kernel.runtime_reflection import ReferenceRuntimeReflection, ReferenceTuningApplier
from kernel.runtime_supervisor import RuntimeSupervisor
from kernel.observability import LiveRuntimeMetrics
from kernel.self_evolution import MemorySoftPolicySource, PolicyAwareValueSystem
from kernel.llm_advisor import (
    KnowledgeAwareReasoning,
    LLMAdvisorReasoning,
    LLMAdvisorPlanner,
)


class KernelBuilder:
    """Turns a ``KernelConfig`` into a wired ``CognitiveKernel``.

    Pure composition: no global state, deterministic for a given config. Extend by adding a
    field to ``KernelConfig`` and a branch here — never by widening ``build_kernel``'s signature.
    """

    def __init__(self, config: KernelConfig) -> None:
        self._cfg = config

    def build(self) -> CognitiveKernel:
        cfg = self._cfg
        shared_clock: NodeLamportClock = cfg.clock if cfg.clock is not None else NodeLamportClock(cfg.node_id)

        world = InMemoryWorldState(cfg.node_id, clock=shared_clock)
        res = SimpleResourceManager()
        attn = SimpleAttention(res)

        # ТЗ-ME-01 + ТЗ-SE-01: SOFT-layer memory evolution wired into deliberation.
        # ТЗ-LIVE-01: use an injected memory store (resumed from JsonMemoryStore) when supplied,
        # else a fresh in-memory store — so the kernel can RESUME its self-evolution across restarts.
        memory = cfg.memory if cfg.memory is not None else InMemoryLayeredMemory()
        memory_evolution = ReferenceMemoryEvolution(shared_clock)
        soft_source = MemorySoftPolicySource(memory)

        val = PolicyAwareValueSystem(soft_source)
        dec = DeterministicDecisionEngine()
        exec_ = DeterministicExecutive(res)
        learn = SimpleLearningPolicy()

        # ТЗ-RE-01: Reasoning shares the node clock so steps carry node causal order.
        # ТЗ-SE-01: surfaces consolidated semantic facts as grounded candidate directions.
        reason = KnowledgeAwareReasoning(shared_clock, attn, soft_source)

        # ТЗ-WM-01: World Model advisor over world state, shares the node clock.
        world_model = ReferenceWorldModel(shared_clock)

        # ТЗ-PL-01: Planner ranks candidates by predicted value-aware utility; Decision picks.
        # ТЗ-SLICE5: wire procedural memory so the planner can bias confidence by past
        # success-rate (experience-informed ranking). None -> no experience bias (legacy).
        planner = ReferencePlanner(shared_clock, world_model=world_model, values=val,
                                  procedural=cfg.procedural)

        # ТЗ-LLM-01: optional LLM advisor behind ILLMAdvisor; None -> pure reference path.
        # NOTE: reason/planner are ALWAYS the LLMAdvisor variants (mirrors the pre-refactor
        # build_kernel): when advisor is None they degrade to the PURE reference path, but
        # they still expose attach_metrics for the live collector below.
        advisor: Optional[ILLMAdvisor] = None
        if cfg.llm_client is not None:
            advisor = cfg.llm_client if isinstance(cfg.llm_client, ILLMAdvisor) else adapter_for(cfg.llm_client)
        reason = LLMAdvisorReasoning(shared_clock, attn, soft_source, advisor=advisor)
        planner = LLMAdvisorPlanner(shared_clock, world_model=world_model, values=val,
                                    advisor=advisor, procedural=cfg.procedural)

        # Флаг 2 / ТЗ-LLM-02: wire live collector into advisor wrappers (no-op if None).
        if cfg.live_metrics is not None:
            if not isinstance(cfg.live_metrics, ILiveMetricsCollector):
                raise TypeError("live_metrics must implement ILiveMetricsCollector")
            reason.attach_metrics(cfg.live_metrics)
            planner.attach_metrics(cfg.live_metrics)

        # ТЗ-RF-01: Reflection Engine (analytic half of Self-Evolving), before Learn.
        reflection_engine = ReferenceReflectionEngine(shared_clock)

        # Флаг 3 (OBS-01): live runtime adaptation from live metrics; no-op without collector.
        supervisor = None
        if cfg.live_metrics is not None:
            live_runtime = LiveRuntimeMetrics(
                cfg.live_metrics, memory_evolution=memory_evolution, clock=shared_clock)
            supervisor = RuntimeSupervisor(
                metrics=live_runtime,
                reflection=ReferenceRuntimeReflection(clock=shared_clock),
                applier=ReferenceTuningApplier(),
                targets={
                    "memory.confidence_threshold": memory_evolution,
                    "memory.min_repetitions": memory_evolution,
                },
                clock=shared_clock,
            )

        kernel = CognitiveKernel(
            world, attn, res, val, dec, exec_, learn, planner,
            clock=shared_clock, reason=reason, world_model=world_model,
            memory_evolution=memory_evolution, memory=memory,
            reflection_engine=reflection_engine, embedding=cfg.embedding,
        )

        # Post-hoc optional wiring (public attach_* API).
        if cfg.live_metrics is not None:
            kernel.attach_live_metrics(cfg.live_metrics, supervisor)
        if cfg.bus is not None:
            # bus currently only meaningful for federation wiring; attach if a federation
            # service is supplied through the (reserved) bus field's metadata.
            federation = getattr(cfg.bus, "federation", None)
            if federation is not None:
                kernel.attach_federation(federation)
        return kernel
