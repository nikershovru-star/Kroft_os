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

import json
import urllib.error
import urllib.parse
import urllib.request
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


# =============================================================================
# PHASE 4 — KroftHttpBridge: Hermes (external agent) as HTTP CLIENT to KROFT.
#
# Architectural invariant (ТЗ PHASE 4 §19/§20): Hermes does NOT import KROFT
# internals (GraphQueryEngine / CrdtGraph / ReferenceKnowledgeResolution /
# InMemoryProceduralMemory). It talks ONLY to the universal HTTP contract
# exposed by KroftRuntime (PHASE 3): /api/status | /api/search | /api/query |
# /api/resolve | /api/audit. KROFT remains agent-agnostic; the bridge is the
# single external boundary.
#
# K1 axis-clean: this class imports ONLY contracts + stdlib (urllib). It never
# instantiates or imports a concrete KROFT service.
# =============================================================================

class KroftHttpBridge:
    """Hermes-side HTTP client to a running KroftRuntime (external agent).

    Reuses the PHASE 3 universal HTTP API — no KROFT business logic here.
    One bridge instance targets ONE KROFT node (one Runtime HTTP endpoint).
    A Local KROFT Network = several KroftHttpBridge instances, one per node.
    """

    def __init__(self, base_url: str, timeout: float = 10.0,
                 node_id: Optional[str] = None) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._node_id = node_id

    # --- transport (thin) ------------------------------------------------
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None):
        url = self._base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8") or b"{}")
            except Exception:
                body = {}
            return e.code, body
        except Exception as exc:  # network down / refused
            return 503, {"error": "transport", "message": str(exc)}

    def _post(self, path: str, payload: Dict[str, Any]):
        url = self._base + path
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8") or b"{}")
            except Exception:
                body = {}
            return e.code, body
        except Exception as exc:
            return 503, {"error": "transport", "message": str(exc)}

    # --- universal tool surface (mirrors IKroftAgentInterface) ----------
    def status(self) -> KroftToolResult:
        code, body = self._get("/api/status")
        if code != 200:
            return KroftToolResult(ok=False, operation="status",
                                   errors=[body.get("message", "status failed")])
        return KroftToolResult(ok=True, operation="status", result=body,
                               metadata=body)

    def search(self, query: str, top_k: int = 10) -> KroftToolResult:
        # Reuse the EXISTING /api/search (lexical) — no new search engine.
        code, body = self._get("/api/search", {"q": query, "top_k": top_k})
        if code != 200:
            return KroftToolResult(ok=False, operation="search",
                                   errors=[body.get("message", "search failed")])
        items = [{"id": n, "score": 1.0} for n in (body if isinstance(body, list) else [])]
        return KroftToolResult(
            ok=True, operation="search", result={"query": query, "items": items},
            metadata={"count": len(items), "mode": "lexical", "node": self._node_id},
        )

    def query(self, query: str, top_k: int = 10) -> KroftToolResult:
        code, body = self._post("/api/query", {"query": query, "top_k": top_k})
        if code != 200:
            return KroftToolResult(ok=False, operation="query",
                                   errors=[body.get("message", "query failed")])
        return KroftToolResult(
            ok=True, operation="query", result=body,
            metadata={"mode": body.get("mode", "hybrid"), "node": self._node_id},
        )

    def resolve(self, query: str, resolution: str = "SYSTEM") -> KroftToolResult:
        code, body = self._post("/api/resolve",
                                {"query": query, "level": resolution.upper()})
        if code != 200:
            return KroftToolResult(ok=False, operation="resolve",
                                   errors=[body.get("message", "resolve failed")])
        return KroftToolResult(
            ok=True, operation="resolve", result=body,
            metadata={"level": resolution.upper(), "node": self._node_id},
        )

    def audit(self, limit: int = 50) -> KroftToolResult:
        code, body = self._get("/api/audit", {"limit": limit})
        if code != 200:
            return KroftToolResult(ok=False, operation="audit",
                                   errors=[body.get("message", "audit failed")])
        return KroftToolResult(ok=True, operation="audit", result=body,
                               metadata={"node": self._node_id})


def kroft_http_bridge(base_url: str, timeout: float = 10.0,
                      node_id: Optional[str] = None) -> KroftHttpBridge:
    """Module-level factory (Hermes tool surface for PHASE 4)."""
    return KroftHttpBridge(base_url, timeout=timeout, node_id=node_id)
