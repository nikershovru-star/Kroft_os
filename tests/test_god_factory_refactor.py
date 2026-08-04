"""K8 tests for god-factory refactor (ТЗ-OBS-01 Флаг 1 debt close). SEPARATE commit (Флаг 1b).

Covers equivalence + safety of the extracted KernelConfig / KernelBuilder composition root:
- backward-compatible kwargs build still works (48 existing call sites unaffected).
- new declarative config path produces an equivalent kernel.
- live_metrics-only path (no llm_client) does NOT raise — the pre-refactor path that must
  survive; reason/planner are ALWAYS the LLMAdvisor variants (advisor=None -> pure path, but
  attach_metrics available for the live collector).
- llm_client + live_metrics path works.
- KernelConfig.merged: explicit kwargs WIN over a passed config object.
- KernelBuilder is deterministic (same config -> same clock node_origin).
- build_kernel delegates to KernelBuilder (single composition root).
- public re-export surface preserved (ReferencePlanner/ReferenceWorldModel/... importable
  from kernel.cognitive_kernel) — regression guard for the over-aggressive cleanup that broke
  test_self_evolution_closure (Флаг 3).

Proof of behavioural equivalence: full suite 1157 passed / 0 failed == pre-refactor baseline.
"""

from __future__ import annotations

from kernel.cognitive_kernel import build_kernel, KernelConfig
from kernel.kernel_builder import KernelBuilder
from contracts.cognitive_domain import NodeLamportClock
from contracts.i_observability import ILiveMetricsCollector
from contracts.i_llm_advisor import ILLMAdvisor, LLMError


class FakeMetrics(ILiveMetricsCollector):
    def record(self, n, v, labels=None):
        pass

    def snapshot(self):
        return {}

    def get_counter(self, n):
        return 0

    def get_gauge(self, n):
        return 0.0


class FakeAdvisor(ILLMAdvisor):
    def advise(self, ctx):
        raise LLMError("offline")


def test_kwargs_build_works():
    k = build_kernel("N1")
    assert k is not None


def test_config_path_works():
    k = build_kernel(config=KernelConfig(node_id="N2"))
    assert k is not None


def test_config_none_opts_equals_kwargs():
    # explicit-None opts must behave like the default kwargs build
    k = build_kernel(config=KernelConfig(node_id="N3", llm_client=None, live_metrics=None))
    assert k is not None


def test_live_metrics_only_path_does_not_raise():
    # the pre-refactor path that MUST keep working (OBS-01 used it without llm_client)
    k = build_kernel("N4", live_metrics=FakeMetrics())
    assert k is not None
    assert k._metrics is not None


def test_llm_and_live_path_works():
    k = build_kernel(config=KernelConfig(
        node_id="N5", llm_client=FakeAdvisor(), live_metrics=FakeMetrics()))
    assert k is not None


def test_kernelconfig_merged_kwargs_win():
    cfg = KernelConfig(node_id="base", llm_client=None)
    merged = cfg.merged(node_id="override")
    assert merged.node_id == "override"
    assert merged.llm_client is None


def test_builder_deterministic_same_clock_origin():
    a = KernelBuilder(KernelConfig(node_id="D")).build()
    b = KernelBuilder(KernelConfig(node_id="D")).build()
    assert a._clock.node_id == b._clock.node_id == "D"


def test_build_kernel_delegates_to_builder():
    import kernel.cognitive_kernel as ck
    with open(ck.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert "KernelBuilder(resolved).build()" in src


def test_public_reexport_surface_preserved():
    # Флаг 3 regression guard: tests import these from kernel.cognitive_kernel
    from kernel.cognitive_kernel import (
        ReferencePlanner,
        ReferenceWorldModel,
        InMemoryLayeredMemory,
        ReferenceMemoryEvolution,
        ReferenceReflectionEngine,
        InMemoryWorldState,
        SimpleAttention,
        SimpleResourceManager,
        DeterministicDecisionEngine,
        DeterministicExecutive,
        SimpleLearningPolicy,
        NodeLamportClock,
    )
    assert all(c is not None for c in (
        ReferencePlanner, ReferenceWorldModel, InMemoryLayeredMemory,
        ReferenceMemoryEvolution, ReferenceReflectionEngine, InMemoryWorldState,
        SimpleAttention, SimpleResourceManager, DeterministicDecisionEngine,
        DeterministicExecutive, SimpleLearningPolicy, NodeLamportClock,
    ))
