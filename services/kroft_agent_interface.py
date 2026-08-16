"""PHASE 2 — KroftAgentInterface (delegate-only concrete impl of IKroftAgentInterface).

REUSE-FIRST (K5): every method delegates to an EXISTING service resolved from the
DI container — GraphQueryEngine (search/query/audit/observe/knowledge) and
ReferenceKnowledgeResolution (ADR-028 Э1, resolve). No second search engine, no
duplicated resolution logic, no agent-specific branching (ТЗ §2: KROFT stays
agnostic to which external agent is calling).

Axis: services.* -> contracts + stdlib (allowed). The container is injected; the
implementation does NOT import concrete adapters/services at module top-level.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from contracts import ResolutionLevel
from contracts.i_kroft_agent_interface import IKroftAgentInterface


class KroftAgentInterface(IKroftAgentInterface):
    """Universal agent-facing facade over a running KROFT Runtime.

    Constructed by the composition/assembly layer with the live DI container and
    (optionally) the KroftRuntime for health/status. Pure delegation — holds no
    business logic of its own.
    """

    def __init__(self, container: Any, runtime: Any = None) -> None:
        self._container = container
        self._runtime = runtime

    # --- helpers ------------------------------------------------------------
    def _engine(self):
        return self._container.resolve("GraphQueryEngine")

    def _resolution(self):
        if self._container.has("ReferenceKnowledgeResolution"):
            return self._container.resolve("ReferenceKnowledgeResolution")
        return None

    def _memory(self):
        if self._container.has("IProceduralMemory"):
            return self._container.resolve("IProceduralMemory")
        return None

    # --- interface ----------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        if self._runtime is not None:
            return self._runtime.health()
        engine = self._engine()
        return {
            "status": "ok",
            "node_id": "kroft-local",
            "runtime": "running",
            "kernel": "ready",
            "knowledge": "ready" if bool(engine._snapshot().get("nodes")) else "empty",
            "http": "n/a",
        }

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        engine = self._engine()
        hits = engine.hybrid_search(query, top_k=top_k)
        return [{"id": nid, "score": float(score), "kind": "hybrid"} for nid, score in hits]

    def query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        engine = self._engine()
        hits = engine.hybrid_search(query, top_k=top_k)
        return {
            "query": query,
            "mode": "hybrid",
            "results": [{"id": nid, "score": float(score)} for nid, score in hits],
            "abstained": len(hits) == 0,
        }

    def resolve(self, query: str, level: str = "SYSTEM") -> Dict[str, Any]:
        svc = self._resolution()
        if svc is None:
            return {
                "ok": False,
                "operation": "resolve",
                "error": "ReferenceKnowledgeResolution not wired into container (GAP)",
            }
        try:
            lvl = ResolutionLevel[level.upper()]
        except KeyError:
            return {
                "ok": False,
                "operation": "resolve",
                "error": f"unknown resolution level: {level}",
                "valid": [l.name for l in ResolutionLevel],
            }
        view = svc.view(query, lvl)
        return {
            "ok": True,
            "operation": "resolve",
            "query": query,
            "level": lvl.name,
            "items": getattr(view, "items", []),
            "resolution": getattr(view, "resolution", lvl.name),
        }

    def audit(self, limit: int = 50) -> Dict[str, Any]:
        engine = self._engine()
        log = engine.get_audit_log()
        return {"ok": True, "operation": "audit", "count": len(log), "entries": log[-limit:]}

    def observe(self, topic: Optional[str] = None) -> Dict[str, Any]:
        engine = self._engine()
        stats = engine.graph_stats()
        health = engine.graph_health()
        out: Dict[str, Any] = {
            "ok": True,
            "operation": "observe",
            "graph_stats": stats,
            "graph_health": health,
        }
        if topic:
            out["topic_hits"] = self.search(topic, top_k=5)
        return out

    def memory(self, action: str = "list", **kwargs: Any) -> Dict[str, Any]:
        mem = self._memory()
        if mem is None:
            return {"ok": False, "operation": "memory", "error": "memory service not wired (GAP)"}
        # Delegate to the existing procedural memory API without re-implementing it.
        try:
            if action == "list":
                items = mem.list_procedures(**kwargs) if hasattr(mem, "list_procedures") else []
                return {"ok": True, "operation": "memory", "action": action, "items": items}
            if action == "stats":
                return {"ok": True, "operation": "memory", "action": action,
                        "stats": mem.stats() if hasattr(mem, "stats") else {}}
        except Exception as exc:  # never crash the agent surface on a memory gap
            return {"ok": False, "operation": "memory", "error": str(exc)}
        return {"ok": False, "operation": "memory", "error": f"unknown action: {action}"}

    def knowledge(self, action: str = "stats", **kwargs: Any) -> Dict[str, Any]:
        engine = self._engine()
        if action == "stats":
            return {"ok": True, "operation": "knowledge", "action": action,
                    "stats": engine.graph_stats()}
        if action == "health":
            return {"ok": True, "operation": "knowledge", "action": action,
                    "health": engine.graph_health()}
        return {"ok": False, "operation": "knowledge", "error": f"unknown action: {action}"}
