"""KernelConfig — declarative composition spec for build_kernel (ТЗ-OBS-01 Флаг 1, debt close).

Replaces the growing positional/keyword argument list + inline `if ... is not None` +
post-hoc `attach_*` blocks in `kernel.cognitive_kernel.build_kernel`. New optional
subsystems (a future ТЗ) are added as a field here + a branch in `KernelBuilder`, NOT as a
new `build_kernel` parameter — so the factory stops growing and wiring stays readable.

Backward-compatible: `build_kernel(node_id=..., llm_client=..., live_metrics=..., bus=...)`
still works; it builds a `KernelConfig` from kwargs and delegates to `KernelBuilder`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from contracts.cognitive_domain import NodeLamportClock
from contracts.i_cognitive_kernel import ILayeredMemory


@dataclass
class KernelConfig:
    """Declarative spec of which optional subsystems to wire into the kernel.

    Every field is Optional: the reference (LLM-free, deterministic, I-09) kernel is the
    default when all optional fields are None. The builder is the single place that turns
    a config into a wired CognitiveKernel.
    """

    node_id: str = "local"
    clock: Optional[NodeLamportClock] = None
    llm_client: Optional[Any] = None          # ILlm model port OR ILLMAdvisor
    live_metrics: Optional[Any] = None        # ILiveMetricsCollector
    bus: Optional[Any] = None                 # IEventBus (federation / runtime)
    # ТЗ-LIVE-01: inject a pre-loaded memory store so a kernel can RESUME across restarts
    # (state replayed from JsonMemoryStore). When None, a fresh in-memory store is built.
    memory: Optional[ILayeredMemory] = None
    # ТЗ-SLICE5: inject a pre-loaded procedural memory (InMemoryProceduralMemory) so the
    # planner can do experience-informed ranking from REAL accumulated success rates.
    # When None, the planner runs without experience bias (backward-compatible).
    procedural: Optional[Any] = None
    # Slice: optional embedding adapter (IEmbedding) for semantic episodic retrieval.
    # None -> keyword-overlap fallback (deterministic, network-free by default).
    embedding: Optional[Any] = None
    # Retrieval-augmented reasoning: an optional pre-built knowledge index (e.g.
    # services.content_index.ContentIndex) the kernel queries during tick to inject
    # top-k corpus context into planning. Duck-typed: any object with .search(text)
    # returning List[str] of node ids works. None -> no knowledge injection (the
    # reference kernel stays LLM-free + deterministic, backward-compatible).
    knowledge_index: Optional[Any] = None

    def merged(self, *, node_id: Any = None, clock: Any = None,
               llm_client: Any = None, live_metrics: Any = None, bus: Any = None,
               memory: Any = None, procedural: Any = None,
               embedding: Any = None, knowledge_index: Any = None) -> "KernelConfig":
        """Return a copy with any supplied kwargs overriding this config's fields.

        Used by the backward-compatible ``build_kernel(...)`` kwargs path: explicit kwargs
        win over a passed ``config=`` object. Mirrors dataclasses.replace semantics but only
        for the fields a caller may pass positionally/by-name.
        """
        return KernelConfig(
            node_id=node_id if node_id is not None else self.node_id,
            clock=clock if clock is not None else self.clock,
            llm_client=llm_client if llm_client is not None else self.llm_client,
            live_metrics=live_metrics if live_metrics is not None else self.live_metrics,
            bus=bus if bus is not None else self.bus,
            memory=memory if memory is not None else self.memory,
            procedural=procedural if procedural is not None else self.procedural,
            embedding=embedding if embedding is not None else self.embedding,
            knowledge_index=knowledge_index if knowledge_index is not None else self.knowledge_index,
        )
