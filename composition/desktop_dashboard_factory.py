"""Desktop dashboard composition (ТЗ-DESKTOP-01, ADR-097, Флаг C).

Standalone wiring (composition root may import kernel + services + adapters; gate rule: composition ->
everything). Builds a DashboardSnapshotter from REAL kernel components using their EXISTING public
accessors — does NOT duplicate any observability/state accessor (K5). The dashboard is READ-ONLY:
every provider is a read closure; nothing is written back to the kernel (O1-style safe observation).

NOT wired into build_kernel (Флаг C) — the dashboard is an opt-in user-facing surface.

Providers per surface (read-only closures):
  node_id        <- kernel._node_id (or injected node_id_provider)
  kernel_state   <- kernel._state.name (or injected state_provider)
  memory_counts  <- memory_platform get_episodes/get_semantic/get_normative lengths
  agents         <- identity_registry.list() ids
  trust          <- trust_registry authors -> trust_score_of
  models         <- model_registry.catalog() ids
  tasks          <- task_store list items (id, status)
Missing components degrade to empty tuples (dashboard still renders).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from contracts.i_dashboard import DashboardSnapshot, IDashboard
from services.desktop_dashboard import DashboardSnapshotter


def _trust_authors(trust_registry: Any) -> List[str]:
    """Return known author ids from a trust registry (read-only, duck-typed)."""
    if trust_registry is None:
        return []
    # Prefer a public accessor if present; otherwise read the internal by_author map
    # (composition may read kernel/identity internals for observability wiring).
    if hasattr(trust_registry, "authors"):
        try:
            return list(trust_registry.authors())
        except Exception:
            pass
    # seed() writes per-author running trust into _running (no recorded items yet)
    running = getattr(trust_registry, "_running", None)
    if isinstance(running, dict) and running:
        return list(running.keys())
    by_author = getattr(trust_registry, "_by_author", None)
    if isinstance(by_author, dict) and by_author:
        return list(by_author.keys())
    return []


def _mem_counts(memory_platform: Any) -> Tuple[int, int, int]:
    """Episode / semantic / normative counts from a memory platform (read-only, duck-typed).

    Supports both the layered memory API (ILayeredMemory: get_episodes/get_semantic/get_normative)
    and the procedural skill memory API (IProceduralMemory: list_skills). Missing methods count 0.
    """
    if memory_platform is None:
        return (0, 0, 0)
    # Layered memory (kernel layered store)
    if hasattr(memory_platform, "get_episodes"):
        try:
            eps = len(memory_platform.get_episodes())
        except Exception:
            eps = 0
        try:
            sem = len(memory_platform.get_semantic())
        except Exception:
            sem = 0
        try:
            nor = len(memory_platform.get_normative())
        except Exception:
            nor = 0
        return (eps, sem, nor)
    # Procedural skill memory (services memory_platform)
    if hasattr(memory_platform, "list_skills"):
        try:
            return (len(memory_platform.list_skills()), 0, 0)
        except Exception:
            return (0, 0, 0)
    return (0, 0, 0)


def _task_pairs(task_store: Any) -> List[Tuple[str, str]]:
    """(task_id, status) pairs from a task store (read-only, duck-typed)."""
    if task_store is None:
        return []
    items = []
    try:
        lst = task_store.list() if hasattr(task_store, "list") else getattr(task_store, "tasks", [])
        if callable(lst):
            lst = lst()
        for t in lst:
            tid = getattr(t, "id", "?")
            status = getattr(t, "status", "?")
            items.append((str(tid), str(status)))
    except Exception:
        pass
    return items


def _installed_skills(skill_repository: Any) -> int:
    """Count installed skills in the local marketplace (read-only, duck-typed)."""
    if skill_repository is None:
        return 0
    installed = getattr(skill_repository, "_installed", None)
    if isinstance(installed, dict):
        return len(installed)
    if hasattr(skill_repository, "installed_count"):
        try:
            return int(skill_repository.installed_count())
        except Exception:
            return 0
    return 0


def _federation_nodes(distributor: Any) -> int:
    """Count reachable federation peers (read-only, duck-typed)."""
    if distributor is None:
        return 0
    peers = getattr(distributor, "_peers", None)
    if isinstance(peers, (set, list, dict, tuple)):
        return len(peers)
    if hasattr(distributor, "peer_count"):
        try:
            return int(distributor.peer_count())
        except Exception:
            return 0
    return 0


def _memory_notes(graph_engine: Any, memory_platform: Any) -> int:
    """Knowledge-graph notes count (read-only, duck-typed). Falls back to layered semantic facts."""
    if graph_engine is not None and hasattr(graph_engine, "nodes"):
        try:
            return len(graph_engine.nodes())
        except Exception:
            pass
    if memory_platform is not None and hasattr(memory_platform, "get_semantic"):
        try:
            return len(memory_platform.get_semantic())
        except Exception:
            pass
    return 0


def _trust_score(trust_registry: Any) -> float:
    """Aggregate trust across known authors (mean of current_trust). 0.0 when empty."""
    authors = _trust_authors(trust_registry)
    if not authors:
        return 0.0
    total = 0.0
    n = 0
    for a in authors:
        try:
            if hasattr(trust_registry, "current_trust"):
                total += float(trust_registry.current_trust(a))
            else:
                total += float(trust_registry.trust_score_of(a))
            n += 1
        except Exception:
            pass
    return (total / n) if n else 0.0


def build_default_dashboard(
    kernel: Any = None,
    memory_platform: Any = None,
    trust_registry: Any = None,
    identity_registry: Any = None,
    task_store: Any = None,
    model_registry: Any = None,
    skill_repository: Any = None,
    distributor: Any = None,
    graph_engine: Any = None,
    logs_buffer: Any = None,
    state_provider: Optional[Callable[[], str]] = None,
    node_id_provider: Optional[Callable[[], str]] = None,
    captured_at: int = 0,
) -> "IDashboard":
    """Wire a read-only DashboardSnapshotter over the given kernel components (Флаг C).

    Every component is OPTIONAL; a missing component simply yields an empty surface. The returned
    dashboard is READ-ONLY — it never mutates the kernel, trust, memory, or task store. ТЗ-RUN-01
    extends the panel with marketplace skills (skill_repository), federation nodes (distributor),
    memory notes (graph_engine / layered semantic), aggregate trust, and a logs ring buffer.
    """
    node_id_fn: Callable[[], str] = node_id_provider or (
        lambda: getattr(kernel, "_node_id", "unknown") if kernel is not None else "unknown"
    )
    state_fn: Callable[[], str] = state_provider or (
        lambda: getattr(getattr(kernel, "_state", None), "name", "unknown")
        if kernel is not None else "unknown"
    )

    providers: Dict[str, Callable[[], object]] = {
        "node_id": node_id_fn,
        "kernel_state": state_fn,
        "memory_counts": lambda: _mem_counts(memory_platform),
        "agents": (
            lambda: [a.agent_id for a in identity_registry.list()]
            if identity_registry is not None else []
        ),
        "trust": (
            lambda: [(aid, trust_registry.trust_score_of(aid)) for aid in _trust_authors(trust_registry)]
            if trust_registry is not None else []
        ),
        "models": (
            lambda: [m.id for m in model_registry.catalog()]
            if model_registry is not None else []
        ),
        "tasks": lambda: _task_pairs(task_store),
        # --- ТЗ-RUN-01 panel aggregates (reuse existing accessors, no new port) ---
        "marketplace_skills": lambda: _installed_skills(skill_repository),
        "federation_nodes": lambda: _federation_nodes(distributor),
        "memory_notes": lambda: _memory_notes(graph_engine, memory_platform),
        "trust_score": lambda: _trust_score(trust_registry),
        "logs": (
            lambda: list(logs_buffer)[-5:] if logs_buffer is not None else []
        ),
    }
    return DashboardSnapshotter(providers, captured_at=captured_at)
