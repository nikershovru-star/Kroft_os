"""Observability dashboard port — read-only kernel state snapshot (ТЗ-DESKTOP-01, ADR-097).

K1-compliant: stdlib + contracts only. K5: this is the ONLY new seam for the desktop layer.
It does NOT duplicate OBS-01 (ILiveMetricsCollector / RuntimeSupervisor — operational RATIO
metrics). OBS-01 answers "how well is the system running?"; this dashboard answers "what is the
current structural STATE of the kernel?" (memory counts, agents, trust, models, tasks, FSM state).
Both are first-class separate boundaries (one-port-per-boundary).

Design (K5, no duplication): DashboardSnapshotter is a PURE renderer/aggregator. It takes READ-ONLY
providers (callables) for each surface and assembles a frozen DashboardSnapshot. The composition
layer (build_default_dashboard) wires the providers to the REAL components (kernel._state, TrustRegistry,
IdentityRegistry, ProceduralMemory, ModelRegistry, TaskStore) using their EXISTING public accessors.
The snapshotter never imports kernel/services/identity — it only knows callables, so it cannot mutate
anything. READ-ONLY is structural: providers return values, the snapshotter writes nothing back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Tuple


@dataclass(frozen=True)
class DashboardSnapshot:
    """Frozen, read-only structural snapshot of the kernel (ТЗ-DESKTOP-01, extended by ТЗ-RUN-01).

    All fields are immutable tuples/dicts captured at snapshot time. `captured_at` is a
    monotonic sequence (Lamport tick or a provided counter) for display ordering only — it is
    NOT a wall-clock timestamp and never feeds back into the kernel (K5 determinism, no time base).

    The dashboard answers "what is the current structural STATE of the whole system?" — kernel
    FSM, agents, tasks, models, marketplace skills, federation nodes, memory notes, trust, logs.
    Counts are derived by the renderer (len of tuple fields) plus explicit aggregate fields for the
    panel (marketplace_skills, federation_nodes, memory_notes, trust_score).
    """
    node_id: str
    kernel_state: str
    memory_counts: Tuple[int, int, int]   # (episodes, semantic_facts, normative_policies)
    agents: Tuple[str, ...]                # registered agent ids
    trust: Tuple[Tuple[str, float], ...]   # (author_id, trust_score) pairs
    models: Tuple[str, ...]               # declared model ids
    tasks: Tuple[Tuple[str, str], ...]     # (task_id, status) pairs
    # --- ТЗ-RUN-01 panel aggregates (reuse existing component accessors, no new port) ---
    marketplace_skills: int = 0           # installed skills in the local marketplace
    federation_nodes: int = 0             # reachable federation peers
    memory_notes: int = 0                 # knowledge-graph notes / semantic facts
    trust_score: float = 0.0              # aggregate trust (mean of registered authors)
    logs: Tuple[str, ...] = ()            # recent log lines (ring buffer)
    captured_at: int = 0


class IDashboard(ABC):
    """Read-only observability dashboard (ТЗ-DESKTOP-01)."""

    @abstractmethod
    def snapshot(self) -> DashboardSnapshot:
        """Capture the current read-only structural state of the kernel."""
        ...

    @abstractmethod
    def render_text(self, snap: DashboardSnapshot) -> str:
        """Render a deterministic human-readable text view."""
        ...

    @abstractmethod
    def render_json(self, snap: DashboardSnapshot) -> str:
        """Render a deterministic JSON view (sorted keys, stable)."""
        ...
