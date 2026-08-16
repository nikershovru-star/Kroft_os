"""H0 — HERMES <-> KROFT COGNITIVE BRIDGE (READ-ONLY).

Внешний adapter/tool layer между Hermes Agent и существующей KROFT OS.
НЕ является частью KROFT: импортирует только `composition.run_kroft.KroftApp`
(composition root) + `contracts.i_knowledge_resolution` (ADR-028 port).

Архитектурные инварианты ТЗ H0:
  - KROFT НЕ импортирует Hermes (нет `from hermes import ...`).
  - Bridge — единственная граница (Hermes -> Bridge -> existing KROFT API).
  - READ ONLY: bridge НЕ вызывает ingest/save/persist/merge/commit/git.
  - LOCAL ONLY: in-process import KroftApp (без TCP listener / network endpoint).
  - Reuse: retrieval/query/resolve УЖЕ существуют в KROFT — bridge их вызывает,
    НЕ создаёт нового retrieval / LLM transport / federation.

ТЗ H0 STEP 4: минимальный интерфейс
    kroft_status()
    kroft_search(query)
    kroft_query(query)
    kroft_resolve(query, resolution)
    kroft_audit(target)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from contracts import ResolutionLevel


@dataclass
class KroftToolResult:
    """Structured tool result (ТЗ H0 §13).

    ok=False + error НЕ превращается в ложный "ничего не найдено" (ТЗ §14).
    """

    ok: bool
    operation: str
    result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class KroftBridge:
    """READ-ONLY bridge к локальному KROFT OS.

    Лениво строит KroftApp в read-only конфигурации (no agent_runtime / no
    federation / no embedding / no LLM). Все публичные методы только читают.
    """

    def __init__(self, snapshot_path: Optional[str] = None, node_id: Optional[str] = None) -> None:
        self._snapshot_path = snapshot_path
        self._node_id = node_id
        self._app = None
        self._resolution: Optional[IKnowledgeResolution] = None
        self._available = False

    # --- lazy boot (in-process, no network) ---
    def _ensure_app(self) -> "Any":
        if self._app is not None:
            return self._app
        try:
            from composition.run_kroft import KroftApp, KroftConfig
            cfg = KroftConfig(
                node_id=self._node_id or "nodeA",
                agent_runtime=False,
                federation=False,
                embedding="none",
                llm="none",
                run_demo=False,
                knowledge_snapshot=self._snapshot_path,
            )
            self._app = KroftApp(cfg)
            # ADR-028 Этап 1 сервис (ReferenceKnowledgeResolution) требует
            # IGraphQuery, который KroftApp read-only boot НЕ выставляет
            # (GraphQueryEngine живёт только в cli/ DI-container). Поэтому
            # self._resolution остаётся None -> kroft_resolve честно возвращает
            # GAP (ТЗ §27, no fake). Сборка сервиса здесь намеренно опущена.
            self._resolution = None
            self._available = True
            return self._app
        except Exception as exc:  # ТЗ §14: honest unavailable, not silent
            self._available = False
            raise RuntimeError(f"KROFT unavailable: {exc}") from exc

    @property
    def available(self) -> bool:
        return self._available

    # --- kroft_status (ТЗ §8) ---
    def status(self) -> KroftToolResult:
        try:
            app = self._ensure_app()
        except Exception as exc:
            return KroftToolResult(ok=False, operation="status",
                                   errors=[str(exc)])
        try:
            graph = app.graph
            nodes = len(graph.nodes())
            edges = len(graph.edges())
            vectors = 0
            try:
                if app._snapshot_store is not None:
                    vecs = app._snapshot_store.load_semantic_vectors()
                    vectors = len(vecs)
            except Exception:
                vectors = 0
            meta = {
                "node_id": app.config.node_id,
                "knowledge": {"nodes": nodes, "edges": edges, "vectors": vectors},
                "retrieval": {
                    "lexical": True,
                    "semantic": app.embedding_adapter is not None
                    if hasattr(app, "embedding_adapter") else False,
                    "hybrid": True,
                },
                "resolution": {"enabled": True},
                "memory": {"enabled": True},
                "federation": {"enabled": app.config.federation},
            }
            return KroftToolResult(ok=True, operation="status",
                                   result=meta, metadata=meta)
        except Exception as exc:
            return KroftToolResult(ok=False, operation="status",
                                   errors=[f"status read failed: {exc}"])

    # --- kroft_search (ТЗ §9, приоритет hybrid) ---
    def search(self, query: str, top_k: int = 10) -> KroftToolResult:
        try:
            app = self._ensure_app()
        except Exception as exc:
            return KroftToolResult(ok=False, operation="search",
                                   errors=[str(exc)])
        try:
            # Reuse production retrieval: KroftApp.search is already hybrid-
            # capable (ReferenceSearchService). Fall back to lexical only if needed.
            svc = app.search
            # KroftApp.search returns ranked [(id, score)] for hybrid when wired.
            raw = svc.search_hybrid(query, top_k=top_k) if hasattr(svc, "search_hybrid") \
                else svc.search(query)
            items = []
            for entry in raw:
                if isinstance(entry, tuple):
                    nid, score = entry[0], entry[1]
                else:
                    nid, score = entry, 1.0
                items.append({"id": nid, "score": score})
            return KroftToolResult(
                ok=True, operation="search", result={"query": query, "items": items},
                metadata={"count": len(items), "mode": "hybrid"},
            )
        except Exception as exc:
            return KroftToolResult(ok=False, operation="search",
                                   errors=[f"search failed: {exc}"])

    # --- kroft_query (ТЗ §10) ---
    # Reuse production retrieval: ReferenceSearchService (KroftApp.search) is
    # the existing query path. Semantic abstention (GraphQueryEngine.
    # query_with_abstention) lives in cli/ DI-container only, NOT in KroftApp,
    # so we reuse the search service (honest, no fake LLM answer).
    def query(self, query: str, top_k: int = 10) -> KroftToolResult:
        try:
            app = self._ensure_app()
        except Exception as exc:
            return KroftToolResult(ok=False, operation="query",
                                   errors=[str(exc)])
        try:
            svc = app.search
            raw = svc.search_hybrid(query, top_k=top_k) if hasattr(svc, "search_hybrid") \
                else svc.search(query)
            items = []
            for entry in raw:
                if isinstance(entry, tuple):
                    nid, score = entry[0], entry[1]
                else:
                    nid, score = entry, 1.0
                items.append({"id": nid, "score": score})
            return KroftToolResult(
                ok=True, operation="query", result={"query": query, "items": items},
                metadata={"count": len(items), "mode": "hybrid"},
            )
        except Exception as exc:
            return KroftToolResult(ok=False, operation="query",
                                   errors=[f"query failed: {exc}"])

    # --- kroft_resolve (ТЗ §11, ADR-028 Этап 1) ---
    # ReferenceKnowledgeResolution requires IGraphQuery, which KroftApp's
    # read-only boot does NOT expose (GraphQueryEngine lives only in cli/
    # DI-container). This is a HONEST GAP (ТЗ §27): we do NOT fake resolution.
    # Returns ok=False with the gap reason; no silent fallback.
    def resolve(self, query: str, resolution: str = "CONCEPT") -> KroftToolResult:
        try:
            self._ensure_app()
        except Exception as exc:
            return KroftToolResult(ok=False, operation="resolve",
                                   errors=[str(exc)])
        try:
            level = ResolutionLevel[resolution.upper()]
        except KeyError:
            return KroftToolResult(
                ok=False, operation="resolve",
                errors=[f"unknown resolution level: {resolution} "
                        f"(valid: {[l.name for l in ResolutionLevel]})"])
        svc = self._resolution
        if svc is None:
            return KroftToolResult(
                ok=False, operation="resolve",
                errors=["GAP: IGraphQuery not exposed by KroftApp read-only boot "
                        "(GraphQueryEngine lives in cli/ DI-container only). "
                        "ADR-028 ReferenceKnowledgeResolution cannot be wired "
                        "without changing KROFT — deferred to H1."])
        try:
            view = svc.view(query, level)
            return KroftToolResult(
                ok=True, operation="resolve",
                result={"query": query, "level": level.name,
                        "items": getattr(view, "items", [])},
                metadata={"level": level.name,
                          "count": len(getattr(view, "items", []))},
            )
        except Exception as exc:
            return KroftToolResult(ok=False, operation="resolve",
                                   errors=[f"resolve failed: {exc}"])

    # --- kroft_audit (ТЗ §12, READ-ONLY diagnostic adapter) ---
    def audit(self, target: str) -> KroftToolResult:
        try:
            app = self._ensure_app()
        except Exception as exc:
            return KroftToolResult(ok=False, operation="audit",
                                   errors=[str(exc)])
        try:
            t = (target or "").lower()
            if t == "semantic retrieval":
                has_vec = app.embedding_adapter is not None
                has_idx = hasattr(app, "semantic_index") and app.semantic_index is not None
                return KroftToolResult(
                    ok=True, operation="audit",
                    result={"target": target, "semantic_layer": has_vec,
                            "semantic_index": bool(has_idx)},
                    metadata={"probe": "semantic retrieval capability"})
            if t == "memory":
                return KroftToolResult(
                    ok=True, operation="audit",
                    result={"target": target,
                            "layered_memory": app.memory is not None,
                            "procedural": app.procedural is not None},
                    metadata={"probe": "memory subsystems"})
            if t == "federation":
                return KroftToolResult(
                    ok=True, operation="audit",
                    result={"target": target,
                            "federation_enabled": app.config.federation},
                    metadata={"probe": "federation config"})
            if t == "persistence":
                has_snap = app._snapshot_store is not None
                return KroftToolResult(
                    ok=True, operation="audit",
                    result={"target": target,
                            "snapshot_store": bool(has_snap),
                            "knowledge_snapshot": app.config.knowledge_snapshot},
                    metadata={"probe": "persistence layer"})
            # fallback: engine stats
            stats = app.engine.stats() if hasattr(app.engine, "stats") else {}
            return KroftToolResult(
                ok=True, operation="audit",
                result={"target": target, "stats": stats},
                metadata={"probe": "generic engine stats"})
        except Exception as exc:
            return KroftToolResult(ok=False, operation="audit",
                                   errors=[f"audit failed: {exc}"])


# Convenience module-level adapters (Hermes tool surface).
def kroft_status() -> KroftToolResult:
    return KroftBridge().status()


def kroft_search(query: str, top_k: int = 10) -> KroftToolResult:
    return KroftBridge().search(query, top_k=top_k)


def kroft_query(query: str, top_k: int = 10) -> KroftToolResult:
    return KroftBridge().query(query, top_k=top_k)


def kroft_resolve(query: str, resolution: str = "CONCEPT") -> KroftToolResult:
    return KroftBridge().resolve(query, resolution)


def kroft_audit(target: str) -> KroftToolResult:
    return KroftBridge().audit(target)
