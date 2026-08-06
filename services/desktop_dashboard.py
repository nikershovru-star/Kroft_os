"""Observability dashboard reference impl — read-only snapshot + deterministic renderer
(ТЗ-DESKTOP-01, ADR-097).

K1: stdlib + contracts only (services layer). K6: imports ONLY contracts.i_dashboard (the port) —
it NEVER imports kernel/identity/services/trust. The snapshotter is a PURE aggregator/renderer that
takes READ-ONLY providers (callables) and assembles a frozen DashboardSnapshot. Because it only knows
callables, it cannot mutate any kernel state — READ-ONLY is structural.

Renderer determinism (I-09): render_json uses sort_keys so byte output is stable across runs; render_text
uses sorted tuples. No wall-clock time is embedded in the snapshot (captured_at is an injected sequence).
"""

from __future__ import annotations

import json
from typing import Callable, Dict, Tuple

from contracts.i_dashboard import DashboardSnapshot, IDashboard


def _safe(provider: Callable[[], object], default: object) -> object:
    """Call a provider; on any failure return the default (dashboard must never raise on read)."""
    try:
        return provider()
    except Exception:
        return default


class DashboardSnapshotter(IDashboard):
    """Read-only kernel-state snapshotter + text/JSON renderer (ТЗ-DESKTOP-01, Флаг C-free).

    `providers` maps surface name -> a zero-arg callable returning that surface's current value:
      - node_id:        () -> str
      - kernel_state:   () -> str
      - memory_counts:  () -> (episodes, semantic, normative)
      - agents:         () -> Sequence[str]
      - trust:          () -> Sequence[(author_id, score)]
      - models:         () -> Sequence[str]
      - tasks:          () -> Sequence[(task_id, status)]
      - marketplace_skills: () -> int   (installed skills in local marketplace)
      - federation_nodes:   () -> int   (reachable federation peers)
      - memory_notes:       () -> int   (knowledge-graph notes / semantic facts)
      - trust_score:        () -> float (aggregate trust, mean of authors)
      - logs:               () -> Sequence[str]  (recent log lines)
    Each provider is read-only; the snapshotter writes nothing back (O1-style safe observation).
    """

    def __init__(self, providers: Dict[str, Callable[[], object]],
                 captured_at: int = 0) -> None:
        self._providers = providers
        self._captured_at = captured_at

    def snapshot(self) -> DashboardSnapshot:
        node_id = str(_safe(self._providers.get("node_id", lambda: "unknown"), "unknown"))
        state = str(_safe(self._providers.get("kernel_state", lambda: "unknown"), "unknown"))
        mem = _safe(self._providers.get("memory_counts", lambda: (0, 0, 0)), (0, 0, 0))
        agents = tuple(_safe(self._providers.get("agents", lambda: ()), ()))
        trust = tuple(_safe(self._providers.get("trust", lambda: ()), ()))
        models = tuple(_safe(self._providers.get("models", lambda: ()), ()))
        tasks = tuple(_safe(self._providers.get("tasks", lambda: ()), ()))
        marketplace = int(_safe(self._providers.get("marketplace_skills", lambda: 0), 0))
        federation = int(_safe(self._providers.get("federation_nodes", lambda: 0), 0))
        notes = int(_safe(self._providers.get("memory_notes", lambda: 0), 0))
        trust_score = float(_safe(self._providers.get("trust_score", lambda: 0.0), 0.0))
        logs = tuple(_safe(self._providers.get("logs", lambda: ()), ()))
        # Normalize memory_counts to a 3-tuple of ints (defensive against provider shape drift).
        try:
            mem_t = tuple(int(x) for x in mem[:3])
        except Exception:
            mem_t = (0, 0, 0)
        while len(mem_t) < 3:
            mem_t = mem_t + (0,)
        return DashboardSnapshot(
            node_id=node_id,
            kernel_state=state,
            memory_counts=mem_t,
            agents=tuple(str(a) for a in agents),
            trust=tuple((str(a), float(s)) for a, s in trust),
            models=tuple(str(m) for m in models),
            tasks=tuple((str(t), str(st)) for t, st in tasks),
            marketplace_skills=marketplace,
            federation_nodes=federation,
            memory_notes=notes,
            trust_score=trust_score,
            logs=tuple(str(l) for l in logs),
            captured_at=self._captured_at,
        )

    def render_text(self, snap: DashboardSnapshot) -> str:
        """Render the KROFT Desktop control panel (ТЗ-RUN-01): system-at-a-glance layout."""
        model_lines = [f"  {m}" for m in sorted(snap.models)] if snap.models else ["  -"]
        log_lines = ["  " + l for l in snap.logs[-5:]] if snap.logs else ["  ..."]
        lines = [
            "KROFT Desktop",
            "──────────────────────────",
            "Kernel",
            f"  {'✓ Running' if snap.kernel_state not in ('STOPPED', 'FAILED') else '✗ ' + snap.kernel_state}",
            "",
            "Agents",
            f"  {len(snap.agents)} active",
            "",
            "Tasks",
            f"  {len(snap.tasks)} queued",
            "",
            "Models",
            *model_lines,
            "",
            "Marketplace",
            f"  {snap.marketplace_skills} skills",
            "",
            "Federation",
            f"  {snap.federation_nodes} nodes",
            "",
            "Memory",
            f"  {snap.memory_notes} notes",
            "",
            "Trust",
            f"  {snap.trust_score:.2f}",
            "",
            "Logs",
            *log_lines,
            "──────────────────────────",
        ]
        return "\n".join(lines)

    def render_json(self, snap: DashboardSnapshot) -> str:
        payload = {
            "node_id": snap.node_id,
            "kernel_state": snap.kernel_state,
            "memory_counts": {
                "episodes": snap.memory_counts[0],
                "semantic": snap.memory_counts[1],
                "normative": snap.memory_counts[2],
            },
            "agents": sorted(snap.agents),
            "trust": {a: s for a, s in sorted(snap.trust)},
            "models": sorted(snap.models),
            "tasks": {t: st for t, st in sorted(snap.tasks)},
            "marketplace_skills": snap.marketplace_skills,
            "federation_nodes": snap.federation_nodes,
            "memory_notes": snap.memory_notes,
            "trust_score": snap.trust_score,
            "logs": list(snap.logs[-5:]),
            "captured_at": snap.captured_at,
        }
        # sort_keys -> deterministic byte output (I-09). separators compact.
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
