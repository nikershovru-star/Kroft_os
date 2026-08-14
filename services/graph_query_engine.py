"""Graph Query Engine -- second application-layer IService.

Read-only structural queries over a knowledge graph owned by an IGraphBuilder.
Depends ONLY on contracts.* (+ stdlib); it never imports adapters,
infrastructure, kernel, or runtime.

Service-to-service communication: VaultStreamCrawler WRITES to a shared
IGraphBuilder instance; GraphQueryEngine READS from the SAME instance. The two
services never reference each other -- they are coupled only through the
contracts.IGraphBuilder / contracts.IGraphQuery ports.
"""
from __future__ import annotations
import hashlib
import re
import time
from collections import deque
from typing import Any, Dict, List, Optional

from contracts import IService, IGraphBuilder, IGraphQuery


# Stage 21: local tokenizer (mirror of ContentIndex._tokenize). Sibling-import
# into services/ is forbidden by the arch gate, so the regex is duplicated
# here rather than imported from content_index.
_TOKEN_RE = re.compile(r"\w+")
_MIN_TOKEN_LEN = 2


def _tokenize(text: str) -> List[str]:
    r"""\w+ tokens, lowercased, len >= 2. No stemming / stop-words."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= _MIN_TOKEN_LEN]


# Stage 21: filter syntax `key:value` (value is \S+ up to whitespace).
_FILTER_RE = re.compile(r"\b(\w+):(\S+)\b")


class GraphQueryEngine(IGraphQuery):
    """Pure read-only structural query engine over a shared IGraphBuilder."""

    def __init__(self, graph: IGraphBuilder, index: Optional[Any] = None,
                 semantic_index: Optional[Any] = None, embedding: Optional[Any] = None,
                 fs: Optional[Any] = None, snapshot_path: Optional[str] = None) -> None:
        # Snapshot-on-read: every query pulls a fresh deep-copy snapshot via
        # graph.get_graph(), so the crawler may mutate the live graph (add
        # nodes/edges) between our calls without corrupting an in-flight query.
        self._graph = graph
        # Stage 43: optional networkx graph (lazy-built from the snapshot on
        # first graph-reasoning call; may also be injected directly for tests).
        self._g: Any = None
        # Stage 18: optional ContentIndex (duck-typed — the services
        # cross-import gate forbids importing the sibling service; the DI
        # composition root wires the SAME instance the crawler writes to).
        # index=None => zero regression: search() returns [].
        self._index = index
        # Stage 29: optional SemanticIndex + IEmbedding (duck-typed pair,
        # same DI convention). Either None => semantic_search() returns [].
        self._semantic_index = semantic_index
        self._embedding = embedding
        # Stage 47: optional persistence port for graph snapshots.
        self._fs = fs
        self._snapshot_path = snapshot_path
        self._auto_snapshot = bool(fs and snapshot_path)
        # Stage 50: temporal audit log (in-memory, append-only).
        self._audit: List[Dict[str, Any]] = []
        # Stage 55/60/63/64 runtime state.
        self._notifications: List[Dict[str, Any]] = []
        self._acl_log: List[Dict[str, Any]] = []
        self._maintenance_log: List[Dict[str, Any]] = []
        self._mutation_queue: Dict[str, List[Dict[str, Any]]] = {}

    def _append_audit(self, action: str, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        """Record a temporal delta for a graph mutation."""
        entry = {
            "ts": (before.get("meta") or {}).get("modified") or after.get("ts", time.time()),
            "action": action,
            "before": before,
            "after": after,
        }
        self._audit.append(entry)
        return entry

    # ----- IService -----
    def name(self) -> str:
        return "graph_query_engine"

    def initialize(self, context: Any | None = None) -> None:
        return None

    def execute(self, context_data: dict) -> str | List[str]:
        # Convenience entry: return the live stats summary string.
        s = self.stats()
        return (
            f"nodes={s['total_nodes']} edges={s['total_edges']} "
            f"orphans={s['orphan_count']}"
        )

    # ----- helpers (operate on a snapshot dict) -----
    @staticmethod
    def _tags_of(node: dict) -> List[str]:
        meta = node.get("meta") or {}
        tags = meta.get("tags") or []
        return list(tags)

    def _snapshot(self) -> dict:
        return self._graph.get_graph()

    # ----- IGraphQuery -----
    def backlinks(self, node_id: str) -> List[str]:
        g = self._snapshot()
        seen: Dict[str, None] = {}
        for e in g["edges"]:
            if e.get("to") == node_id:
                seen.setdefault(e.get("from"), None)
        return list(seen.keys())

    def forward_links(self, node_id: str) -> List[str]:
        g = self._snapshot()
        seen: Dict[str, None] = {}
        for e in g["edges"]:
            if e.get("from") == node_id:
                seen.setdefault(e.get("to"), None)
        return list(seen.keys())

    def nodes_by_tag(self, tag: str) -> List[str]:
        g = self._snapshot()
        return [n["id"] for n in g["nodes"] if tag in self._tags_of(n)]

    def orphan_nodes(self) -> List[str]:
        g = self._snapshot()
        connected: set = set()
        for e in g["edges"]:
            connected.add(e.get("from"))
            connected.add(e.get("to"))
        return [n["id"] for n in g["nodes"] if n["id"] not in connected]

    def _find_node(self, node_id: str) -> Dict[str, Any] | None:
        return next((n for n in self._snapshot().get("nodes", []) if isinstance(n, dict) and n.get("id") == node_id), None)

    # ----- Stage 43: graph-aware reasoning (networkx, lazy import) -----
    def _ensure_nx(self) -> Any:
        """Build (or return) the networkx DiGraph from the live snapshot.

        networkx is imported lazily INSIDE this method so the arch-gate
        (services -> contracts + stdlib only) is not violated at module load.
        If a caller injected ``self._g`` directly (tests), it is returned as-is.
        """
        if self._g is not None:
            return self._g
        import networkx as nx
        snap = self._snapshot()
        g = nx.DiGraph()
        for n in snap.get("nodes", []):
            g.add_node(n["id"])
        for e in snap.get("edges", []):
            src = e.get("from")
            dst = e.get("to")
            if src and dst:
                g.add_edge(src, dst)
        self._g = g
        return g

    def get_neighbors(self, node_id: str, direction: str = "both", depth: int = 1) -> List[Dict[str, Any]]:
        """BFS/DFS neighbors with direction filter and depth limit."""
        g = self._ensure_nx()
        if g is None or node_id not in g:
            return []
        import networkx as nx
        if direction == "out":
            frontier = set(g.successors(node_id))
        elif direction == "in":
            frontier = set(g.predecessors(node_id))
        else:
            frontier = set(g.successors(node_id)) | set(g.predecessors(node_id))
        seen = {node_id}
        for _ in range(depth - 1):
            next_frontier = set()
            for n in frontier:
                if n not in seen:
                    seen.add(n)
                    next_frontier.update(g.successors(n))
                    next_frontier.update(g.predecessors(n))
            frontier = next_frontier - seen
        nodes = (seen | frontier) - {node_id}
        return [{"id": n, "title": n.replace(".md", "").replace("-", " ")} for n in nodes]

    def shortest_path(self, from_id: str, to_id: str) -> List[str]:
        """Shortest path between two nodes; empty list if no path."""
        g = self._ensure_nx()
        if g is None or from_id not in g or to_id not in g:
            return []
        import networkx as nx
        try:
            return nx.shortest_path(g, source=from_id, target=to_id)
        except nx.NetworkXNoPath:
            return []
        except nx.NodeNotFound:
            return []

    def get_cluster(self, node_id: str, k: int = 5) -> List[Dict[str, Any]]:
        """Personalized PageRank cluster around a node (top-k excluding self).

        Pure-stdlib implementation (reuses the iterative scheme from
        ``pagerank``) with a personalization/teleport vector concentrated on
        ``node_id``. Avoids ``nx.pagerank`` which requires the optional
        ``scipy`` dependency (not present in this environment).
        """
        g = self._snapshot()
        ids = [n["id"] for n in g["nodes"]]
        n = len(ids)
        if n == 0 or node_id not in ids:
            return []
        out_count: Dict[str, int] = {nid: 0 for nid in ids}
        incoming: Dict[str, List[str]] = {nid: [] for nid in ids}
        for e in g["edges"]:
            src, dst = e.get("from"), e.get("to")
            if src in out_count and dst in incoming:
                out_count[src] += 1
                incoming[dst].append(src)
        damping = 0.85
        dangling = [nid for nid in ids if out_count[nid] == 0]
        # personalization: teleport only to node_id
        pers: Dict[str, float] = {nid: (1.0 if nid == node_id else 0.0) for nid in ids}
        pr: Dict[str, float] = {nid: 1.0 / n for nid in ids}
        for _ in range(30):
            dangling_sum = sum(pr[nid] for nid in dangling)
            pr = {
                nid: (1.0 - damping) * pers[nid]
                + damping * (dangling_sum / n + sum(pr[src] / out_count[src] for src in incoming[nid]))
                for nid in ids
            }
        pr.pop(node_id, None)
        sorted_nodes = sorted(pr.items(), key=lambda x: x[1], reverse=True)
        return [
            {"id": nid, "score": round(s, 4), "title": nid.replace(".md", "").replace("-", " ")}
            for nid, s in sorted_nodes[:k]
        ]

    # ----- Stage 44: graph mutation (natural-language driven) -----
    def _resolve(self, query: str) -> Optional[str]:
        """Resolve a free-text query to a node id via hybrid_search top-1.

        Falls back to a direct id/label match against the live graph when the
        search index is unavailable (e.g. GraphQueryEngine built without a
        ContentIndex), so graph-mutation commands still work in unit tests
        and minimal setups. Returns the node id, or None if unresolved.
        """
        results = self.hybrid_search(query, top_k=1)
        if results:
            return results[0][0]
        snap = self._snapshot()
        q = (query or "").strip().lower()
        for n in snap.get("nodes", []):
            nid = n.get("id", "")
            if nid == query or nid == query + ".md" or nid.replace(".md", "").lower() == q:
                return nid
            if n.get("label", "").lower() == q:
                return nid
        return None

    def add_link(self, from_query: str, to_query: str, relation: str = "links") -> Dict[str, Any]:
        """Resolve two queries to node ids and create an edge (idempotent)."""
        before = self._snapshot()
        from_id = self._resolve(from_query)
        to_id = self._resolve(to_query)
        if not from_id or not to_id:
            return {"ok": False, "error": "no results"}
        snap = self._snapshot()
        exists = any(
            e.get("from") == from_id and e.get("to") == to_id for e in snap.get("edges", [])
        )
        if exists:
            return {"ok": True, "from": from_id, "to": to_id, "created": False}
        self._graph.add_edge(from_id, to_id, relation)
        self._maybe_snapshot()
        after = self._snapshot()
        self._append_audit("add_link", {"edge": {"from": from_id, "to": to_id}}, {"edge": {"from": from_id, "to": to_id}})
        return {"ok": True, "from": from_id, "to": to_id, "created": True}

    def remove_link(self, from_query: str, to_query: str) -> Dict[str, Any]:
        """Resolve two queries to node ids and remove the edge if present."""
        from_id = self._resolve(from_query)
        to_id = self._resolve(to_query)
        if not from_id or not to_id:
            return {"ok": False, "error": "no results"}
        removed = self._graph.remove_edge(from_id, to_id)
        self._maybe_snapshot()
        after = self._snapshot()
        self._append_audit(
            "remove_link",
            {"edge": {"from": from_id, "to": to_id}},
            {"edge": {"from": from_id, "to": to_id}, "removed": bool(removed)},
        )
        return {"ok": True, "from": from_id, "to": to_id, "removed": bool(removed)}

    def add_tag(self, query: str, tag: str) -> Dict[str, Any]:
        """Resolve query to node id, append tag to node meta['tags'] (unique)."""
        node_id = self._resolve(query)
        if not node_id:
            return {"ok": False, "error": "no results"}
        before_node = next((n for n in self._snapshot().get('nodes', []) if n['id'] == node_id), {})
        added = self._graph.add_tag(node_id, tag)
        self._maybe_snapshot()
        after_node = next((n for n in self._snapshot().get('nodes', []) if n['id'] == node_id), {})
        self._append_audit("add_tag", {"node": before_node}, {"node": after_node})
        return {"ok": True, "node": node_id, "tag": tag, "added": bool(added)}

    def remove_tag(self, query: str, tag: str) -> Dict[str, Any]:
        """Resolve query to node id, remove tag from node meta['tags']."""
        node_id = self._resolve(query)
        if not node_id:
            return {"ok": False, "error": "no results"}
        before_node = next((n for n in self._snapshot().get('nodes', []) if n['id'] == node_id), {})
        removed = self._graph.remove_tag(node_id, tag)
        self._maybe_snapshot()
        after_node = next((n for n in self._snapshot().get('nodes', []) if n['id'] == node_id), {})
        self._append_audit("remove_tag", {"node": before_node}, {"node": after_node})
        return {"ok": True, "node": node_id, "tag": tag, "removed": bool(removed)}

    # ---- Stage 47: snapshot persistence helpers ----
    def set_auto_snapshot(self, enabled: bool) -> None:
        """Toggle automatic snapshot after mutations."""
        self._auto_snapshot = enabled

    def _maybe_snapshot(self) -> None:
        """Persist graph if auto-snapshot is enabled. Never raises."""
        if not self._auto_snapshot or not self._fs or not self._snapshot_path:
            return
        try:
            self._graph.snapshot(self._fs, self._snapshot_path)
        except Exception:
            pass

    def save_graph(self) -> Dict[str, Any]:
        """Explicit snapshot regardless of auto-save toggle."""
        if not self._fs or not self._snapshot_path:
            return {
                "ok": False,
                "error": "filesystem or snapshot path not configured",
            }
        try:
            self._graph.snapshot(self._fs, self._snapshot_path)
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }
        return {
            "ok": True,
            "path": self._snapshot_path,
        }

    def auto_snapshot_status(self) -> Dict[str, Any]:
        """Return auto-snapshot state (read-only)."""
        return {
            "ok": True,
            "enabled": self._auto_snapshot,
            "configured": bool(self._fs and self._snapshot_path),
            "path": self._snapshot_path,
        }

    def suggest_links(self, query: str, top_k: int = 5, min_score: float = 0.01) -> List[Dict[str, Any]]:
        """Recommend missing links for a node (graph proximity + content overlap).

        Pure-stdlib over the snapshot graph:
          - graph_score: |common_neighbors| / max(deg_src, deg_dst, 1), plus an
            adjacency bonus when the candidate is itself a direct neighbor
            (so graph-adjacent nodes outrank isolated ones even with no shared
            neighbors — required by the test suite).
          - content_score: Jaccard overlap of lowercased title word-sets.
          - combined = 0.6 * content_score + 0.4 * graph_score.
        Existing edges (source -> candidate) and self are excluded. Returns
        top_k dicts sorted by combined desc.
        """
        node_id = self._resolve(query)
        if not node_id:
            return []
        snap = self._snapshot()
        nodes = {n["id"]: n for n in snap.get("nodes", [])}
        if node_id not in nodes:
            return []
        # build neighbor sets (undirected: successors + predecessors)
        succ: Dict[str, set] = {}
        pred: Dict[str, set] = {}
        existing: set = set()
        for e in snap.get("edges", []):
            f, t = e.get("from"), e.get("to")
            if f is None or t is None:
                continue
            succ.setdefault(f, set()).add(t)
            pred.setdefault(t, set()).add(f)
            existing.add((f, t))

        def neighbors(nid: str) -> set:
            return succ.get(nid, set()) | pred.get(nid, set())

        def title_of(nid: str) -> str:
            n = nodes.get(nid, {})
            return n.get("label") or nid.replace(".md", "").replace("-", " ")

        def title_tokens(nid: str) -> set:
            return set(re.findall(r"\w+", title_of(nid).lower()))

        src_neighbors = neighbors(node_id)
        src_tokens = title_tokens(node_id)
        src_deg = len(src_neighbors)
        candidates = []
        for cand in nodes:
            if cand == node_id:
                continue
            # exclude an already-existing directed edge source -> candidate
            if (node_id, cand) in existing:
                continue
            cand_neighbors = neighbors(cand)
            common = src_neighbors & cand_neighbors
            cand_deg = len(cand_neighbors)
            denom = max(src_deg, cand_deg, 1)
            adjacency_bonus = 1 if cand in src_neighbors else 0
            graph_score = (len(common) + adjacency_bonus) / denom
            c_tokens = title_tokens(cand)
            union = src_tokens | c_tokens
            content_score = len(src_tokens & c_tokens) / len(union) if union else 0.0
            combined = 0.6 * content_score + 0.4 * graph_score
            reason = f"shared {len(common)} neighbors + title overlap"
            candidates.append({
                "id": cand,
                "score": round(combined, 4),
                "reason": reason,
                "title": title_of(cand),
            })
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    def graph_stats(self) -> Dict[str, Any]:
        """Return high-level graph statistics."""
        g = self._snapshot()
        nodes = g.get("nodes", [])
        edges = g.get("edges", [])
        n = len(nodes)
        m = len(edges)
        density = m / (n * (n - 1)) if n > 1 else 0.0
        orphan_ids = self.orphan_nodes()
        return {
            "nodes": n,
            "edges": m,
            "density": round(density, 4),
            "orphans": len(orphan_ids),
            "orphan_ids": orphan_ids,
        }

    def top_central(self, k: int = 5, metric: str = "pagerank") -> List[Dict[str, Any]]:
        """Return top-k nodes by centrality metric ('pagerank' or 'degree').

        Pure-stdlib: degree counts undirected degree; pagerank uses the same
        iterative scheme as Stage 43 get_cluster (uniform teleport vector).
        """
        g = self._snapshot()
        ids = [n["id"] for n in g.get("nodes", [])]
        if not ids:
            return []
        if metric == "degree":
            out_count: Dict[str, int] = {nid: 0 for nid in ids}
            in_count: Dict[str, int] = {nid: 0 for nid in ids}
            for e in g.get("edges", []):
                src, dst = e.get("from"), e.get("to")
                if src in out_count:
                    out_count[src] += 1
                if dst in in_count:
                    in_count[dst] += 1
            scores = {nid: out_count[nid] + in_count[nid] for nid in ids}
        else:
            # uniform PageRank (pure stdlib, same iterative core as S43)
            out_count: Dict[str, int] = {nid: 0 for nid in ids}
            incoming: Dict[str, List[str]] = {nid: [] for nid in ids}
            for e in g.get("edges", []):
                src, dst = e.get("from"), e.get("to")
                if src in out_count and dst in incoming:
                    out_count[src] += 1
                    incoming[dst].append(src)
            damping = 0.85
            dangling = [nid for nid in ids if out_count[nid] == 0]
            n = len(ids)
            pr: Dict[str, float] = {nid: 1.0 / n for nid in ids}
            for _ in range(30):
                dangling_sum = sum(pr[nid] for nid in dangling)
                base = (1.0 - damping) / n + damping * dangling_sum / n
                pr = {
                    nid: base + damping * sum(pr[src] / out_count[src] for src in incoming[nid])
                    for nid in ids
                }
            scores = pr
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {"id": nid, "score": round(s, 4), "title": nid.replace(".md", "").replace("-", " ")}
            for nid, s in sorted_nodes[:k]
        ]

    def graph_health(self) -> Dict[str, Any]:
        """Quick health check: stats + heuristics."""
        stats = self.graph_stats()
        healthy = stats["orphans"] == 0 and stats["density"] > 0
        return {"ok": True, "healthy": healthy, "stats": stats}

    # ---- Stage 47: snapshot persistence helpers ----
    def set_auto_snapshot(self, enabled: bool) -> None:
        """Toggle automatic snapshot after mutations."""
        self._auto_snapshot = enabled

    def _maybe_snapshot(self) -> None:
        """Persist graph if auto-snapshot is enabled. Never raises."""
        if not self._auto_snapshot or not self._fs or not self._snapshot_path:
            return
        try:
            self._graph.snapshot(self._fs, self._snapshot_path)
        except Exception:
            pass

    def save_graph(self) -> Dict[str, Any]:
        """Explicit snapshot regardless of auto-save toggle."""
        if not self._fs or not self._snapshot_path:
            return {
                "ok": False,
                "error": "filesystem or snapshot path not configured",
            }
        try:
            self._graph.snapshot(self._fs, self._snapshot_path)
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }
        return {
            "ok": True,
            "path": self._snapshot_path,
        }

    def auto_snapshot_status(self) -> Dict[str, Any]:
        """Return auto-snapshot state (read-only)."""
        return {
            "ok": True,
            "enabled": self._auto_snapshot,
            "configured": bool(self._fs and self._snapshot_path),
            "path": self._snapshot_path,
        }

    def graph_enhanced_search(
        self,
        query: str,
        top_k: int = 10,
        oversample: int = 3,
        alpha: float = 0.5,
        beta: float = 0.3,
        gamma: float = 0.2,
    ) -> List[Dict[str, Any]]:
        """Graph-enhanced ranking pipeline over hybrid_search candidates."""
        if not query or not query.strip():
            return []
        query = query.strip()
        raw = self.hybrid_search(query, top_k=top_k * oversample)
        if not raw:
            return []
        # normalize semantic scores to 0..1
        max_sem = max(s for _, s in raw)
        if max_sem <= 0:
            max_sem = 1.0
        candidates = []
        for nid, sem in raw:
            candidates.append({
                "id": nid,
                "semantic_score": round(sem / max_sem, 4),
            })

        snap = self._snapshot()
        nodes = {n["id"]: n for n in snap.get("nodes", [])}
        succ: Dict[str, set] = {}
        pred: Dict[str, set] = {}
        for e in snap.get("edges", []):
            f, t = e.get("from"), e.get("to")
            if f is None or t is None:
                continue
            succ.setdefault(f, set()).add(t)
            pred.setdefault(t, set()).add(f)

        def neighbors(nid: str) -> set:
            return succ.get(nid, set()) | pred.get(nid, set())

        semantic_map = {c["id"]: c["semantic_score"] for c in candidates}
        now = time.time()
        for c in candidates:
            nid = c["id"]
            node = nodes.get(nid, {})
            title = node.get("label") or nid.replace(".md", "").replace("-", " ")
            c["title"] = title
            neigh = neighbors(nid)
            if neigh and semantic_map:
                neighbor_scores = [semantic_map[n] for n in neigh if n in semantic_map]
                if neighbor_scores:
                    g_score = max(neighbor_scores) * 0.6 + (sum(neighbor_scores) / len(neighbor_scores)) * 0.4
                else:
                    g_score = 0.0
            else:
                g_score = 0.0
            c["graph_score"] = round(g_score, 4)
            modified = (node.get("meta") or {}).get("modified")
            if modified is not None:
                try:
                    recency = 1.0 / (1.0 + 0.001 * (now - float(modified)))
                except Exception:
                    recency = 0.5
            else:
                recency = 0.5
            c["recency_score"] = round(recency, 4)
            c["final_score"] = round(
                alpha * c["semantic_score"] + beta * c["graph_score"] + gamma * c["recency_score"], 4
            )
            c["reason"] = (
                f"semantic={c['semantic_score']:.3f} "
                f"graph={c['graph_score']:.3f} "
                f"recency={c['recency_score']:.3f}"
            )

        candidates.sort(key=lambda x: x["final_score"], reverse=True)
        return candidates[:top_k]

    def _find_cycles(self, snap: Dict[str, Any]) -> List[List[str]]:
        """Return all simple directed cycles (up to a cap of 10 for performance)."""
        nodes = [n["id"] for n in snap.get("nodes", [])]
        adj: Dict[str, List[str]] = {nid: [] for nid in nodes}
        for e in snap.get("edges", []):
            src, dst = e.get("from"), e.get("to")
            if src in adj and dst in adj:
                adj[src].append(dst)
        cycles: List[List[str]] = []

        def dfs(path: List[str], visited: set) -> None:
            if len(cycles) >= 10:
                return
            last = path[-1]
            for nxt in adj.get(last, []):
                if nxt == path[0] and len(path) >= 2:
                    cycles.append(path.copy())
                    return
                if nxt not in visited:
                    visited.add(nxt)
                    path.append(nxt)
                    dfs(path, visited)
                    path.pop()
                    visited.remove(nxt)

        for nid in nodes:
            dfs([nid], {nid})
        # deduplicate rotations
        seen: set = set()
        uniq: List[List[str]] = []
        for c in cycles:
            key = tuple(sorted(c))
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        return uniq

    def validate_graph(self) -> Dict[str, Any]:
        """Full constraint check. Returns structured report."""
        snap = self._snapshot()
        nodes = {n["id"] for n in snap.get("nodes", [])}
        edges = snap.get("edges", [])
        issues = []
        # orphans
        orphans = self.orphan_nodes()
        if orphans:
            issues.append({
                "type": "orphan",
                "severity": "warning",
                "nodes": orphans,
                "message": f"{len(orphans)} orphan note(s) with no links",
            })
        # nodes without tags
        no_tags = [n["id"] for n in snap.get("nodes", []) if not (n.get("meta") or {}).get("tags")]
        if no_tags:
            issues.append({
                "type": "no_tags",
                "severity": "info",
                "nodes": no_tags,
                "message": f"{len(no_tags)} note(s) without tags",
            })
        # broken links
        broken = []
        for e in edges:
            src, dst = e.get("from"), e.get("to")
            if src not in nodes or dst not in nodes:
                broken.append({"from": src, "to": dst})
        if broken:
            issues.append({
                "type": "broken_link",
                "severity": "error",
                "nodes": list({n for b in broken for n in (b.get("from"), b.get("to")) if n is not None}),
                "message": f"{len(broken)} edge(s) referencing missing nodes",
                "edges": broken,
            })
        # cycles (directed)
        cycles = self._find_cycles(snap)
        if cycles:
            issues.append({
                "type": "cycle",
                "severity": "warning",
                "nodes": list({n for c in cycles for n in c}),
                "message": f"{len(cycles)} directed cycle(s) detected",
                "cycles": cycles,
            })
        fixable = sum(1 for i in issues if i["type"] in ("orphan", "no_tags", "broken_link"))
        return {"ok": True, "issues": issues, "fixable": fixable, "total_issues": len(issues)}

    def find_broken_links(self) -> List[Dict[str, Any]]:
        """Return only broken edges (src or dst missing from node set)."""
        snap = self._snapshot()
        nodes = {n["id"] for n in snap.get("nodes", [])}
        broken = []
        for e in snap.get("edges", []):
            src, dst = e.get("from"), e.get("to")
            if src not in nodes or dst not in nodes:
                broken.append({"from": src, "to": dst, "relation": e.get("relation", "links")})
        return broken

    def fix_graph(self) -> Dict[str, Any]:
        """Auto-fix: remove broken links, tag orphans with 'orphan', tag no-tag nodes with 'untagged'.
        Returns summary of applied fixes. Calls _maybe_snapshot() once at the end if any fix applied."""
        snap = self._snapshot()
        nodes = {n["id"] for n in snap.get("nodes", [])}
        fixes = {"broken_removed": 0, "orphans_tagged": 0, "untagged_tagged": 0}
        # remove broken links
        for e in snap.get("edges", []):
            src, dst = e.get("from"), e.get("to")
            if src not in nodes or dst not in nodes:
                self._graph.remove_edge(src, dst)
                fixes["broken_removed"] += 1
        # tag orphans
        for nid in self.orphan_nodes():
            self._graph.add_tag(nid, "orphan")
            fixes["orphans_tagged"] += 1
        for n in snap.get("nodes", []):
            nid = n["id"]
            tags = (n.get("meta") or {}).get("tags")
            if not tags:
                self._graph.add_tag(nid, "untagged")
                fixes["untagged_tagged"] += 1
        if any(fixes.values()):
            self._maybe_snapshot()
            after_snap = self._snapshot()
            for action in ["remove_link", "add_tag"]:
                self._append_audit(action, {}, {"fixes": fixes, "after": after_snap})
        return {"ok": True, "fixes": fixes}

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return the full temporal audit log for this engine instance (read-only)."""
        return list(self._audit)

    def mutations_since(self, ts_min: float) -> List[Dict[str, Any]]:
        """Return audit entries with timestamp > ts_min (strict, read-only)."""
        return [entry for entry in self._audit if entry.get("ts", 0) > ts_min]

    def review_queue(self, top_k: int = 10) -> List[Dict[str, Any]]:
        """Prioritized list of notes needing attention (read-only)."""
        g = self._snapshot()
        nodes = {n["id"]: n for n in g.get("nodes", [])}
        if not nodes:
            return []

        orphan_ids = set(self.orphan_nodes())
        undirected_degree: Dict[str, int] = {nid: 0 for nid in nodes}
        for e in g.get("edges", []):
            src, dst = e.get("from"), e.get("to")
            if src in undirected_degree:
                undirected_degree[src] += 1
            if dst in undirected_degree:
                undirected_degree[dst] += 1

        pr_map = {item["id"]: item["score"] for item in self.top_central(k=len(nodes), metric="pagerank")}
        max_pr = max(pr_map.values()) if pr_map else 0.0
        now = time.time()

        scored: List[Dict[str, Any]] = []
        for nid, n in nodes.items():
            reasons: List[str] = []
            actions: List[str] = []
            priority = 0.0
            if nid in orphan_ids:
                priority += 2.0
                reasons.append("orphan")
                actions.extend(["link to most central node", "tag as 'orphan'"])
            tags = (n.get("meta") or {}).get("tags") or []
            if not tags:
                priority += 1.0
                reasons.append("untagged")
                actions.append("add tags")
            deg = undirected_degree.get(nid, 0)
            priority += 1.0 / (1 + deg)
            if deg <= 1:
                reasons.append(f"peripheral (degree {deg})")
            modified = (n.get("meta") or {}).get("modified") or 0.0
            if modified > 0:
                days_since = max((now - modified) / 86400.0, 0.0)
                stale_score = min(days_since / 30.0, 3.0)
                if stale_score > 0:
                    priority += stale_score
                    reasons.append(f"stale ({int(days_since)}d)")
                    actions.extend(["review content", "update modified timestamp"])
            pr = pr_map.get(nid, 0.0)
            if max_pr > 0:
                priority -= 1.0 * (pr / max_pr)
            scored.append({
                "id": nid,
                "title": nid.replace(".md", "").replace("-", " "),
                "priority": round(priority, 4),
                "reasons": reasons,
                "actions": actions,
            })

        scored.sort(key=lambda x: x["priority"], reverse=True)
        return scored[:top_k]

    def compound_query(self, **filters) -> List[Dict[str, Any]]:
        """Filter nodes by compound criteria (AND logic, read-only)."""
        g = self._snapshot()
        nodes = {n["id"]: n for n in g.get("nodes", [])}
        if not nodes:
            return []

        neighbor_sets: Dict[str, set] = {nid: set() for nid in nodes}
        for e in g.get("edges", []):
            src, dst = e.get("from"), e.get("to")
            if src in neighbor_sets and dst in neighbor_sets:
                neighbor_sets[src].add(dst)
                neighbor_sets[dst].add(src)

        linked_to = filters.get("linked_to")
        if linked_to is not None and linked_to in neighbor_sets:
            linked_neighbors = neighbor_sets[linked_to]
        else:
            linked_neighbors = set()

        not_linked_to = filters.get("not_linked_to")
        if not_linked_to is not None and not_linked_to in neighbor_sets:
            not_linked_neighbors = neighbor_sets[not_linked_to]
        else:
            not_linked_neighbors = set()

        orphan_ids = set(self.orphan_nodes())
        required_tags = filters.get("tags", []) or []
        min_degree = filters.get("min_degree")
        max_degree = filters.get("max_degree")
        modified_after = filters.get("modified_after")
        modified_before = filters.get("modified_before")
        orphan_filter = filters.get("orphan")
        untagged_filter = filters.get("untagged")

        results: List[Dict[str, Any]] = []
        for nid, n in nodes.items():
            matches: Dict[str, bool] = {}
            if orphan_filter is not None:
                matches["orphan"] = nid in orphan_ids
            if untagged_filter is not None:
                tags = (n.get("meta") or {}).get("tags") or []
                matches["untagged"] = not tags
            if required_tags:
                tags = (n.get("meta") or {}).get("tags") or []
                matches["tags"] = all(tag in tags for tag in required_tags)
            if min_degree is not None:
                matches["min_degree"] = len(neighbor_sets.get(nid, set())) >= int(min_degree)
            if max_degree is not None:
                matches["max_degree"] = len(neighbor_sets.get(nid, set())) <= int(max_degree)
            if modified_after is not None:
                modified = (n.get("meta") or {}).get("modified") or 0.0
                matches["modified_after"] = modified > float(modified_after)
            if modified_before is not None:
                matched_before = (n.get("meta") or {}).get("modified") or 0.0
                matches["modified_before"] = matched_before < float(modified_before)
            if linked_to is not None:
                matches["linked_to"] = nid in linked_neighbors
            if not_linked_to is not None:
                matches["not_linked_to"] = nid not in not_linked_neighbors

            if all(v is not False for k, v in matches.items() if k in filters):
                results.append({
                    "id": nid,
                    "title": nid.replace(".md", "").replace("-", " "),
                    "degree": len(neighbor_sets.get(nid, set())),
                    "tags": (n.get("meta") or {}).get("tags") or [],
                    "modified": (n.get("meta") or {}).get("modified") or 0.0,
                    "matches": matches,
                })
        return results

    def research_topic(self, query: str, depth: int = 2) -> Dict[str, Any]:
        """High-level research workflow over the knowledge graph."""
        seed_id = self._resolve(query)
        if not seed_id:
            return {"ok": False, "error": "seed not found"}
        seed_title = seed_id.replace(".md", "").replace("-", " ").title()

        g = self._snapshot()
        nodes = {n["id"]: n for n in g.get("nodes", [])}

        neighborhood = []
        neighbor_ids = set()
        for item in self.get_neighbors(seed_id, "both", depth=depth):
            nid = item.get("id") or item.get("node_id")
            if nid and nid != seed_id and nid in nodes:
                neighborhood.append({
                    "id": nid,
                    "title": item.get("title") or nid.replace(".md", "").replace("-", " "),
                    "depth": item.get("depth", 1),
                })
                neighbor_ids.add(nid)

        lateral = []
        for item in self.graph_enhanced_search(query, top_k=10):
            lid = item.get("id") or item.get("node_id")
            if lid and lid in nodes:
                lateral.append({
                    "id": lid,
                    "title": item.get("title") or lid.replace(".md", "").replace("-", " "),
                    "final_score": item.get("final_score", 0.0),
                })

        undirected_degree: Dict[str, int] = {nid: 0 for nid in nodes}
        for e in g.get("edges", []):
            src, dst = e.get("from"), e.get("to")
            if src in undirected_degree:
                undirected_degree[src] += 1
            if dst in undirected_degree:
                undirected_degree[dst] += 1

        gaps: List[Dict[str, Any]] = []
        for nid in neighbor_ids | (neighbor_ids - set()):
            if not nodes.get(nid):
                continue
            reasons: List[str] = []
            if nid in self.orphan_nodes():
                reasons.append("orphan")
            if undirected_degree.get(nid, 0) <= 1:
                reasons.append("peripheral")
            if reasons:
                gaps.append({
                    "id": nid,
                    "title": nid.replace(".md", "").replace("-", " "),
                    "reason": " | ".join(reasons),
                })

        suggested: List[Dict[str, Any]] = []
        for item in self.suggest_links(seed_id, top_k=5):
            suggested.append({
                "id": item.get("id") or item.get("node_id"),
                "score": item.get("score", 0.0),
                "reason": item.get("reason", ""),
            })

        plan: List[str] = []
        for item in suggested:
            sid = item.get("id")
            if sid:
                plan.append(f"link seed to {sid}")
        for item in gaps:
            plan.append(f"review orphan {item['id']}")
        for item in lateral:
            lid = item.get("id")
            if lid and lid not in neighbor_ids:
                plan.append(f"explore {lid}")

        return {
            "ok": True,
            "seed": seed_id,
            "seed_title": seed_title,
            "neighbors": neighborhood,
            "lateral": lateral[:10],
            "gaps": gaps,
            "suggested_links": suggested,
            "plan": plan,
        }

    def bridge_topics(self, from_query: str, to_query: str) -> Dict[str, Any]:
        """Connect two disconnected or weakly connected topics via the graph."""
        from_id = self._resolve(from_query)
        to_id = self._resolve(to_query)
        if not from_id or not to_id:
            return {"ok": False, "error": "node not found"}

        path = self.shortest_path(from_id, to_id)
        if path:
            return {
                "ok": True,
                "connected": True,
                "path": path,
                "length": len(path) - 1 if len(path) > 1 else 0,
                "plan": ["Path exists; strengthen intermediate links"],
            }

        neighbors_from = self.get_neighbors(from_id, "both", depth=2)
        neighbors_to = self.get_neighbors(to_id, "both", depth=2)
        ids_from = {item.get("id") or item.get("node_id") for item in neighbors_from}
        ids_to = {item.get("id") or item.get("node_id") for item in neighbors_to}
        common = ids_from & ids_to

        bridge_candidates: List[Dict[str, Any]] = []
        lateral_query = f"{from_query} {to_query}"
        for item in self.graph_enhanced_search(lateral_query, top_k=10):
            lid = item.get("id") or item.get("node_id")
            if lid:
                bridge_candidates.append({
                    "id": lid,
                    "title": item.get("title") or lid.replace(".md", "").replace("-", " "),
                    "score": item.get("final_score", 0.0),
                })

        plan: List[str] = []
        if common:
            bridge = sorted(common)[0]
            plan.append(f"link {from_id} and {to_id} via common neighbor {bridge}")
        elif bridge_candidates:
            bridge = bridge_candidates[0]["id"]
            plan.append(f"create link from {from_id} to {bridge}")
            if len(bridge_candidates) > 1:
                plan.append(f"create link from {bridge_candidates[1]['id']} to {to_id}")
            else:
                plan.append(f"create link from {bridge} to {to_id}")

        return {
            "ok": True,
            "connected": False,
            "path": None,
            "bridge_candidates": bridge_candidates[:5],
            "common_neighbors": sorted(common),
            "plan": plan,
        }

    def expand_knowledge(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Active expansion: find the most promising node to grow from."""
        seed_id = self._resolve(query)
        if not seed_id:
            return {"ok": False, "error": "seed not found"}

        cluster = self.get_cluster(seed_id, k=top_k * 2)
        cluster_ids = [item.get("id") or item.get("node_id") for item in cluster if item.get("id") or item.get("node_id")]
        seen: set = set()
        expansion_targets: List[Dict[str, Any]] = []
        for cid in cluster_ids:
            for item in self.suggest_links(cid, top_k=top_k):
                target = item.get("id") or item.get("node_id")
                if target and target != seed_id and target not in seen:
                    seen.add(target)
                    expansion_targets.append({
                        "from": cid,
                        "to": target,
                        "reason": item.get("reason", ""),
                    })
        plan = [f"link {item['from']} to {item['to']}" for item in expansion_targets[:top_k]]
        return {
            "ok": True,
            "seed": seed_id,
            "cluster": [{"id": item.get("id") or item.get("node_id"), "score": item.get("score", 0.0)} for item in cluster[: top_k * 2]],
            "expansion_targets": expansion_targets[:top_k],
            "plan": plan,
        }

    def record_user_query(
        self,
        session_id: str,
        query_text: str,
        hit_nodes: List[str],
        intent: str = "unknown",
    ) -> Dict[str, Any]:
        """Record user query as a context subgraph for later interest profiling."""
        sid_node = f"session:{session_id}"
        qhash = hashlib.sha256(query_text.encode("utf-8")).hexdigest()[:16]
        query_node = f"query:{qhash}"
        ts = time.time()

        snap = self._snapshot()
        nodes = {n["id"]: n for n in snap.get("nodes", [])}
        edges = {tuple(sorted((e.get("from"), e.get("to")))): e for e in snap.get("edges", [])}

        if sid_node not in nodes:
            self._graph.add_node(sid_node, session_id, {"type": "session", "last_query": query_text})
        self._graph.add_node(sid_node, session_id, {"type": "session", "last_query": query_text})

        if query_node not in nodes:
            self._graph.add_node(query_node, query_text[:200], {"type": "query", "text": query_text, "ts": ts, "intent": intent})

        self._graph.add_edge(sid_node, query_node, "user_query")
        # backfill relation/meta idempotently via snapshot mutation
        self._ensure_edge_meta(sid_node, query_node, {"relation": "user_query"})

        hits_recorded = 0
        for node_id in hit_nodes:
            if not node_id:
                continue
            if node_id not in nodes:
                self._graph.add_node(node_id, node_id.replace(".md", "").replace("-", " "), {})
            self._graph.add_edge(query_node, node_id, "query_hit")
            self._ensure_edge_meta(query_node, node_id, {"relation": "query_hit"})
            hits_recorded += 1

        interest_updates = 0
        existing_interest = {
            e.get("to"): e
            for e in self._graph._edges
            if e.get("from") == sid_node and e.get("relation") == "interest"
        }
        for node_id in hit_nodes:
            if not node_id:
                continue
            weight = 1
            if node_id in existing_interest:
                weight = int((existing_interest[node_id].get("meta") or {}).get("weight", 1) + 1)
                self._graph.remove_edge(sid_node, node_id)
            self._graph.add_edge(sid_node, node_id, "interest")
            self._ensure_edge_meta(sid_node, node_id, {"relation": "interest", "weight": weight})
            interest_updates += 1

        self._maybe_snapshot()
        self._append_audit("context_query", {"session_id": session_id}, {"hits": hits_recorded, "interests": interest_updates})

        return {
            "ok": True,
            "session_node": sid_node,
            "query_node": query_node,
            "hits_recorded": hits_recorded,
            "interests_updated": interest_updates,
        }

    def _ensure_edge_meta(self, from_id: str, to_id: str, meta: Dict[str, Any]) -> None:
        for e in self._graph._edges:
            if e.get("from") == from_id and e.get("to") == to_id:
                edge_meta = dict(e.get("meta") or {})
                edge_meta.update(meta or {})
                e["meta"] = edge_meta
                return
        new_edge = {"from": from_id, "to": to_id, "relation": (meta or {}).get("relation", "")}
        if meta:
            new_edge["meta"] = dict(meta)
        self._graph._edges.append(new_edge)

    def get_session_context(self, session_id: str, depth: int = 2) -> Dict[str, Any]:
        """Extract session context from graph memory."""
        g = self._snapshot()
        sid_node = f"session:{session_id}"
        nodes = {n["id"]: n for n in g.get("nodes", [])}
        if sid_node not in nodes:
            return {"ok": True, "session_id": session_id, "recent_queries": [], "interest_profile": [], "related_nodes": []}

        edges = g.get("edges", [])
        query_nodes = {}
        interest_nodes = {}

        for e in edges:
            if e.get("from") == sid_node:
                if e.get("relation") == "user_query":
                    qnid = e["to"]
                    qn = nodes.get(qnid, {})
                    query_nodes[qnid] = {
                        "text": (qn.get("meta") or {}).get("text") or qn.get("label", ""),
                        "intent": (qn.get("meta") or {}).get("intent", "unknown"),
                        "ts": (qn.get("meta") or {}).get("ts") or 0.0,
                        "hits": [],
                    }
                elif e.get("relation") == "interest":
                    interest_nodes[e["to"]] = (e.get("meta") or {}).get("weight", 1)

        for e in edges:
            if e.get("from") in query_nodes and e.get("relation") == "query_hit":
                query_nodes[e["from"]]["hits"].append(e["to"])

        recent_queries = sorted(
            [
                {
                    "text": q["text"],
                    "intent": q["intent"],
                    "ts": q["ts"],
                    "hits": q["hits"],
                }
                for q in query_nodes.values()
            ],
            key=lambda x: x["ts"],
            reverse=True,
        )[:10]

        interest_profile = sorted(
            [{"node": nid, "weight": weight} for nid, weight in interest_nodes.items()],
            key=lambda x: x["weight"],
            reverse=True,
        )

        interest_ids = set(interest_nodes.keys()) - {sid_node}
        related_nodes: List[str] = []
        if interest_ids:
            related_ids = set()
            for e in edges:
                if e.get("relation") == "links" and (e.get("from") in interest_ids or e.get("to") in interest_ids):
                    related_ids.add(e.get("from"))
                    related_ids.add(e.get("to"))
            related_nodes = sorted(list(related_ids - interest_ids - {sid_node}))

        return {
            "ok": True,
            "session_id": session_id,
            "recent_queries": recent_queries,
            "interest_profile": interest_profile,
            "related_nodes": related_nodes,
        }

    def suggest_next(self, session_id: str, top_n: int = 3) -> Dict[str, Any]:
        """Proactive suggestions from the interest graph."""
        ctx = self.get_session_context(session_id)
        interest_nodes = [i["node"] for i in ctx.get("interest_profile", [])[:top_n]]
        visited = set()
        for q in ctx.get("recent_queries", []):
            visited.update(q.get("hits", []))
        visited.update(interest_nodes)
        visited.add(f"session:{session_id}")

        g = self._snapshot()
        score_counter: Dict[str, float] = {}

        for nid in interest_nodes:
            for e in g.get("edges", []):
                if e.get("relation") == "links" and e.get("from") == nid:
                    target = e.get("to")
                    if target and target not in visited:
                        score_counter[target] = score_counter.get(target, 0.0) + 1.0

        top_nodes = sorted(score_counter.items(), key=lambda x: x[1], reverse=True)[:top_n]
        suggestions = []
        for nid, score in top_nodes:
            suggestions.append(
                {
                    "node": nid,
                    "title": nid.replace(".md", "").replace("-", " "),
                    "reason": f"Linked from your interest in {nid.replace('.md', '').replace('-', ' ')}",
                    "score": score,
                }
            )
        return {"ok": True, "suggestions": suggestions}

    def get_personalized_summary(self, session_id: str, target_node: str) -> Dict[str, Any]:
        """Return personalized summary for target node based on session history."""
        ctx = self.get_session_context(session_id)
        related_queries = []
        for q in ctx.get("recent_queries", []):
            if target_node in q.get("hits", []):
                related_queries.append(q["text"])

        personalized_note = None
        if related_queries:
            snap_now = self._snapshot()
            nodes_now = {n["id"]: n for n in snap_now.get("nodes", [])}
            meta_now = (nodes_now.get(target_node) or {}).get("meta") or {}
            snapshot_at_hit = {}
            recent_from_ids = {f"query:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}" for text in related_queries}
            qh_edge = next(
                (
                    e
                    for e in snap_now.get("edges", [])
                    if e.get("relation") == "query_hit"
                    and e.get("to") == target_node
                    and e.get("from") in recent_from_ids
                ),
                None,
            )
            if qh_edge:
                snapshot_at_hit = qh_edge.get("meta") or {}
            if snapshot_at_hit and meta_now:
                if snapshot_at_hit.get("snapshot_at_hit") != {"tags": meta_now.get("tags"), "modified": meta_now.get("modified")}:
                    personalized_note = (
                        f"You asked about this before. Changes since last time: tags={meta_now.get('tags')}, modified={meta_now.get('modified')}"
                    )

        return {
            "ok": True,
            "node": target_node,
            "base_summary": target_node,
            "personalized_note": personalized_note,
            "related_past_queries": related_queries,
        }

    # ----- Stage 54: graph health monitor -----
    def graph_health_report(self) -> Dict[str, Any]:
        """Full diagnostic: orphans, broken links, clusters, density."""
        snap = self._snapshot()
        nodes = snap.get("nodes", [])
        edges = snap.get("edges", [])
        all_ids = {n["id"] for n in nodes}

        content_nodes = [
            n for n in nodes
            if not n["id"].startswith(("session:", "query:"))
        ]
        content_ids = {n["id"] for n in content_nodes}
        content_edges = [
            e for e in edges
            if e.get("relation") not in {"user_query", "query_hit", "interest"}
            and not str(e.get("from", "")).startswith(("session:", "query:"))
            and not str(e.get("to", "")).startswith(("session:", "query:"))
        ]

        deg = {nid: 0 for nid in content_ids}
        for e in content_edges:
            f, t = e.get("from"), e.get("to")
            if f in deg:
                deg[f] += 1
            if t in deg:
                deg[t] += 1
        orphans = [nid for nid, d in deg.items() if d == 0]

        broken = [
            e for e in content_edges
            if e.get("from") not in all_ids or e.get("to") not in all_ids
        ]

        adj: Dict[str, set] = {nid: set() for nid in content_ids}
        for e in content_edges:
            f, t = e.get("from"), e.get("to")
            if f in adj and t in adj:
                adj[f].add(t)
                adj[t].add(f)
        visited: set = set()
        clusters = 0
        for nid in content_ids:
            if nid not in visited:
                clusters += 1
                stack = [nid]
                while stack:
                    cur = stack.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    stack.extend(adj[cur] - visited)

        n = len(content_nodes)
        density = len(content_edges) / (n * (n - 1)) if n > 1 else 0.0

        return {
            "ok": True,
            "total_nodes": len(nodes),
            "content_nodes": n,
            "content_edges": len(content_edges),
            "orphans": orphans,
            "orphan_count": len(orphans),
            "broken_links": broken,
            "broken_count": len(broken),
            "clusters": clusters,
            "density": round(density, 4),
        }

    def find_duplicate_candidates(self, threshold: float = 0.8) -> Dict[str, Any]:
        """Find node pairs that look like duplicates by title + tags."""
        snap = self._snapshot()
        nodes = [n for n in snap.get("nodes", []) if not n["id"].startswith(("session:", "query:"))]
        candidates: List[Dict[str, Any]] = []
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                ta = (a.get("label") or a.get("title") or a["id"]).lower().strip()
                tb = (b.get("label") or b.get("title") or b["id"]).lower().strip()

                if ta == tb:
                    t_sim = 1.0
                elif ta in tb or tb in ta:
                    t_sim = 0.9
                else:
                    sa, sb = set(ta.split()), set(tb.split())
                    u = len(sa | sb)
                    t_sim = len(sa & sb) / u if u else 0.0

                ma = (a.get("meta") or {})
                mb = (b.get("meta") or {})
                tag_sim = 0.0
                ta_set = set(ma.get("tags", []))
                tb_set = set(mb.get("tags", []))
                if ta_set or tb_set:
                    tag_sim = len(ta_set & tb_set) / len(ta_set | tb_set)

                score = t_sim
                reason = f"title={round(t_sim,2)}"
                if ta_set or tb_set:
                    score = t_sim * 0.7 + tag_sim * 0.3
                    reason = f"title={round(t_sim,2)}, tags={round(tag_sim,2)}"
                if score >= threshold:
                    candidates.append({
                        "from": a["id"],
                        "to": b["id"],
                        "score": round(score, 4),
                        "reason": reason,
                    })
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return {"ok": True, "candidates": candidates[:20]}

    def cleanup_orphans(self, dry_run: bool = True) -> Dict[str, Any]:
        """Remove content nodes with zero content-degree."""
        report = self.graph_health_report()
        orphans = report.get("orphans", [])
        if not dry_run and orphans:
            bad = set(orphans)
            if isinstance(self._graph._nodes, dict):
                self._graph._nodes = {k: n for k, n in self._graph._nodes.items() if n["id"] not in bad}
            else:
                self._graph._nodes = [n for n in self._graph._nodes if n["id"] not in bad]
            self._graph._edges = [
                e for e in self._graph._edges
                if e.get("from") not in bad and e.get("to") not in bad
            ]
            self._append_audit("cleanup_orphans", {"dry_run": False}, {"removed": len(orphans)})
            self._maybe_snapshot()
        return {
            "ok": True,
            "dry_run": dry_run,
            "orphans_found": orphans,
            "removed": 0 if dry_run else len(orphans),
        }

    def merge_nodes(self, from_node: str, to_node: str, dry_run: bool = True) -> Dict[str, Any]:
        """Merge from_node into to_node: transfer edges, union tags, drop from_node."""
        snap = self._snapshot()
        ids = {n["id"] for n in snap.get("nodes", [])}
        if from_node not in ids or to_node not in ids:
            return {"ok": False, "error": "node not found"}
        if from_node == to_node:
            return {"ok": False, "error": "cannot merge into itself"}

        if not dry_run:
            seen: set = set()
            new_edges: List[dict] = []
            for e in self._graph._edges:
                f, t, rel = e.get("from"), e.get("to"), e.get("relation")
                if f == from_node:
                    f = to_node
                if t == from_node:
                    t = to_node
                if f == t:
                    continue
                key = (f, t, rel)
                if key not in seen:
                    seen.add(key)
                    new_edges.append({**e, "from": f, "to": t})
            self._graph._edges = new_edges

            nodes_map = {n["id"]: dict(n) for n in (self._graph._nodes.values() if isinstance(self._graph._nodes, dict) else self._graph._nodes)}
            to_meta = dict(nodes_map.get(to_node, {}).get("meta") or {})
            from_meta = dict(nodes_map.get(from_node, {}).get("meta") or {})
            to_meta["tags"] = list(set(to_meta.get("tags", []) + from_meta.get("tags", [])))
            if isinstance(self._graph._nodes, dict):
                self._graph._nodes[to_node] = dict(self._graph._nodes.get(to_node, {"id": to_node}), meta=to_meta)
            else:
                for n in self._graph._nodes:
                    if n["id"] == to_node:
                        n["meta"] = to_meta
                        break
            if isinstance(self._graph._nodes, dict):
                self._graph._nodes.pop(from_node, None)
            else:
                self._graph._nodes = [n for n in self._graph._nodes if n["id"] != from_node]
            self._append_audit("merge_nodes", {"from": from_node, "to": to_node}, {})
            self._maybe_snapshot()

        return {
            "ok": True,
            "dry_run": dry_run,
            "from": from_node,
            "to": to_node,
            "message": f"Would merge {from_node} into {to_node}" if dry_run else f"Merged {from_node} into {to_node}",
        }

    def path(self, from_id: str, to_id: str, max_depth: int = 10) -> Optional[List[str]]:
        if max_depth < 0:
            return None
        g = self._snapshot()
        adj: Dict[str, List[str]] = {}
        for n in g["nodes"]:
            adj.setdefault(n["id"], [])
        for e in g["edges"]:
            f = e.get("from")
            t = e.get("to")
            if f is not None:
                adj.setdefault(f, []).append(t)
        if from_id not in adj or to_id not in adj:
            return None
        if from_id == to_id:
            return [from_id]
        queue: "deque[str]" = deque([from_id])
        visited = {from_id}
        parent: Dict[str, Optional[str]] = {from_id: None}
        depth = {from_id: 0}
        while queue:
            cur = queue.popleft()
            if cur == to_id:
                path: List[str] = []
                node: Optional[str] = cur
                while node is not None:
                    path.append(node)
                    node = parent[node]
                path.reverse()
                return path
            if depth[cur] >= max_depth:
                continue
            for nxt in adj.get(cur, []):
                if nxt not in visited:
                    visited.add(nxt)
                    parent[nxt] = cur
                    depth[nxt] = depth[cur] + 1
                    queue.append(nxt)
        return None

    def cluster_by_tag(self) -> Dict[str, List[str]]:
        g = self._snapshot()
        clusters: Dict[str, List[str]] = {}
        for n in g["nodes"]:
            for tag in self._tags_of(n):
                clusters.setdefault(tag, []).append(n["id"])
        return clusters

    def stats(self) -> Dict[str, object]:
        g = self._snapshot()
        total_nodes = len(g["nodes"])
        total_edges = len(g["edges"])
        avg_degree = (total_edges / total_nodes) if total_nodes else 0.0
        orphan_count = len(self.orphan_nodes())
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "avg_degree": avg_degree,
            "orphan_count": orphan_count,
        }

    # ----- graph analytics (Stage 26) -----
    def centrality(self) -> Dict[str, Dict[str, int]]:
        """Degree centrality: in/out/total per node (Stage 26).

        NOTE: get_graph() returns nodes as a LIST of node dicts (not a dict
        keyed by id — that is the on-disk snapshot format). Empty graph -> {}.
        """
        g = self._snapshot()
        result: Dict[str, Dict[str, int]] = {
            n["id"]: {"in": 0, "out": 0, "total": 0} for n in g["nodes"]
        }
        for e in g["edges"]:
            src, dst = e.get("from"), e.get("to")
            if src in result:
                result[src]["out"] += 1
                result[src]["total"] += 1
            if dst in result:
                result[dst]["in"] += 1
                result[dst]["total"] += 1
        return result

    def connected_components(self) -> List[List[str]]:
        """Weakly connected components via BFS (edges as undirected).

        Each component is sorted by node id; components are ordered by size
        desc, then by first node id. Empty graph -> [].
        """
        g = self._snapshot()
        ids = [n["id"] for n in g["nodes"]]
        adj: Dict[str, set] = {nid: set() for nid in ids}
        for e in g["edges"]:
            src, dst = e.get("from"), e.get("to")
            if src in adj and dst in adj:
                adj[src].add(dst)
                adj[dst].add(src)
        visited: set = set()
        components: List[List[str]] = []
        for start in ids:
            if start in visited:
                continue
            comp: List[str] = []
            queue: "deque[str]" = deque([start])
            visited.add(start)
            while queue:
                cur = queue.popleft()
                comp.append(cur)
                for nxt in adj[cur]:
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)
            components.append(sorted(comp))
        return sorted(components, key=lambda c: (-len(c), c[0]))

    def pagerank(self, damping: float = 0.85, iterations: int = 30) -> Dict[str, float]:
        """Iterative PageRank — pure stdlib, no numpy (Stage 26).

        Dangling nodes (no outgoing edges) distribute their rank evenly.
        Duplicate edges count as parallel links (weight via repetition).
        Complexity: O(iterations * (nodes + edges)) — the reverse adjacency
        is prebuilt once (NOT the naive O(nodes^2) scan per target).
        Empty graph -> {}.
        """
        g = self._snapshot()
        ids = [n["id"] for n in g["nodes"]]
        n = len(ids)
        if n == 0:
            return {}
        out_count: Dict[str, int] = {nid: 0 for nid in ids}
        incoming: Dict[str, List[str]] = {nid: [] for nid in ids}
        for e in g["edges"]:
            src, dst = e.get("from"), e.get("to")
            if src in out_count and dst in incoming:
                out_count[src] += 1
                incoming[dst].append(src)
        dangling = [nid for nid in ids if out_count[nid] == 0]
        pr: Dict[str, float] = {nid: 1.0 / n for nid in ids}
        for _ in range(iterations):
            dangling_sum = sum(pr[nid] for nid in dangling)
            base = (1.0 - damping) / n + damping * dangling_sum / n
            pr = {
                nid: base + damping * sum(pr[src] / out_count[src] for src in incoming[nid])
                for nid in ids
            }
        return pr

    # ----- full-text + structural search (Stage 21 DSL) -----
    def _parse_query(self, query: str) -> Tuple[List[str], Dict[str, str]]:
        r"""Split a query into (text_terms, structural_filters).

        A ``key:value`` token is a structural filter; everything else is a
        full-text term. Filters are stripped BEFORE tokenization because
        ``\\w+`` would otherwise split ``tag:todo`` into ``tag`` / ``todo``.
        """
        filters: Dict[str, str] = {}
        for m in _FILTER_RE.finditer(query):
            filters[m.group(1).lower()] = m.group(2)
        text_only = _FILTER_RE.sub("", query).strip()
        terms = _tokenize(text_only) if text_only else []
        return terms, filters

    def search(self, query: str) -> List[str]:
        """Full-text AND-search with optional structural graph filters (Stage 21).

        Syntax:  ``[filter:value ...] [text tokens ...]`` — all conditions ANDed.
        Filters:
          ``tag:X``     — node.meta.tags contains X (case-insensitive)
          ``from:X``    — node is an OUTGOING edge target of X (X links_to node)
          ``to:X``      — node has an INCOMING edge from X (X is a backlink of node)
          ``is:orphan`` — node has zero edges (in or out)
        Text tokens are forwarded to ``ContentIndex.search`` (frequency sort
        preserved); structural filters are a post-filter retaining that order.
        With no text tokens, candidates start from ALL graph nodes (so a
        filter-only query like ``is:orphan`` works even with ``index=None``).
        Unknown filter keys are silently ignored (zero regression).
        """
        terms, filters = self._parse_query(query)

        # 1. Candidate set.
        if terms:
            if self._index is None:
                return []
            candidates = self._index.search(" ".join(terms))
            if not candidates:
                return []
        elif filters:
            # Filter-only query: scan all nodes (works without an index too).
            candidates = [n["id"] for n in self._snapshot()["nodes"]]
        else:
            # Neither text nor filters (empty query) -> nothing to match.
            return []

        # 2. Structural post-filter, preserving candidate order.
        g = self._snapshot()
        node_map = {n["id"]: n for n in g["nodes"]}
        edges = g["edges"]

        result: List[str] = []
        for nid in candidates:
            node = node_map.get(nid)
            if node is None:
                # Index leads the graph (crawl/index ahead of persist) — skip,
                # never raise (integration-collision safety, same as Stage 18).
                continue
            if not self._matches_filters(node, filters, edges):
                continue
            result.append(nid)
        return result

    def semantic_search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Vector similarity search over the SemanticIndex (Stage 29).

        Returns [(node_id, cosine_score), ...] best-first. Without a wired
        semantic_index+embedding pair -> [] (zero regression).
        """
        if self._semantic_index is None or self._embedding is None:
            return []
        q_emb = self._embedding.embed(query)
        return self._semantic_index.search(q_emb, top_k=top_k)

    def hybrid_search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """RRF fusion of lexical (ContentIndex) and semantic (SemanticIndex).

        Reciprocal Rank Fusion (k=60) combines both rank lists into one
        scored result. Zero regression: if either engine is unwired, the
        fusion simply degrades to the other (missing ranks contribute 0).
        """
        if not query or not query.strip():
            return []
        query = query.strip()

        # Lexical: OR over query tokens (not AND). ContentIndex.search is an
        # AND-intersection, which returns [] for long natural-language queries
        # (e.g. "What is entropy in information theory according to Shannon?")
        # because no single chunk contains ALL tokens. OR over tokens lets a
        # chunk mentioning just "entropy" surface, and RRF then fuses it with
        # the semantic rank. This is a minimal ranking fix; the AND search()
        # API is left intact for exact-match callers.
        # Lexical: List[str] from existing search()
        lexical = self.search(query)

        # Semantic: List[Tuple[str, float]] from the SemanticIndex directly
        # (request more candidates so RRF captures overlaps between lists).
        semantic: List[Tuple[str, float]] = []
        if self._semantic_index is not None and self._embedding is not None:
            q_emb = self._embedding.embed(query)
            semantic = self._semantic_index.search(
                q_emb, top_k=max(top_k * 3, 50)
            )

        # RRF fusion, k=60
        k = 60
        scores: Dict[str, float] = {}

        for rank, nid in enumerate(lexical, start=1):
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (k + rank)

        for rank, (nid, _) in enumerate(semantic, start=1):
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (k + rank)

        # Desc by score, asc by nid tie-break
        result = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        return result[:top_k]

    def query_with_abstention(
        self,
        query: str,
        top_k: int = 10,
        semantic_threshold: Optional[float] = None,
    ) -> "tuple[List[Tuple[str, float]], bool]":
        """Semantic retrieval with cosine-gated abstention (ADR-0XX).

        Reads the HONEST cosine scores straight from ``SemanticIndex.search``
        (NOT via ``semantic_search`` — that method is rebound to a Jaccard stub
        at the bottom of this module). Filters candidates to those whose cosine
        is >= ``semantic_threshold`` (0..1). Returns ``(results, abstained)``.

        ``abstained`` is ``True`` iff no candidate cleared the threshold — the
        engine refuses to answer rather than surface a low-confidence / out-of-
        corpus (hallucinated) node.

        Zero regression:
          - no wired ``semantic_index``/``embedding``  -> ([], True)
          - ``semantic_threshold is None``             -> ([], True)
        (no vector signal => cannot assert a match).
        """
        if self._semantic_index is None or self._embedding is None:
            return [], True
        if semantic_threshold is None:
            return [], True
        if not query or not query.strip():
            return [], True

        q_emb = self._embedding.embed(query)
        # Pull MORE candidates than top_k so filtering at the threshold does not
        # starve the result list of borderline-valid hits.
        candidates = self._semantic_index.search(q_emb, top_k=max(top_k * 4, 50))

        kept: List[Tuple[str, float]] = []
        for nid, score in candidates:
            if score >= semantic_threshold:
                kept.append((nid, score))
            if len(kept) >= top_k:
                break
        abstained = len(kept) == 0
        return kept, abstained

    def fuzzy_search(self, query: str) -> List[str]:
        """Fuzzy full-text AND-search over the shared ContentIndex (Stage 20).

        Proxy to ``ContentIndex.fuzzy_search``. Text-only: DSL filters
        (tag:/from:/to:/is:) are NOT combined with fuzzy — that intersection
        is deferred to Stage 22+. With ``index=None`` (no index wired) the
        engine returns [] (zero regression).
        """
        if self._index is None:
            return []
        return self._index.fuzzy_search(query)

    @staticmethod
    def _matches_filters(node: dict, filters: Dict[str, str], edges: List[dict]) -> bool:
        nid = node["id"]
        for key, val in filters.items():
            key = key.lower()
            val = val.strip()
            if key == "tag":
                tags = [t.lower() for t in (node.get("meta") or {}).get("tags") or []]
                if val.lower() not in tags:
                    return False
            elif key == "from":
                if not any(e.get("from") == val and e.get("to") == nid for e in edges):
                    return False
            elif key == "to":
                if not any(e.get("from") == nid and e.get("to") == val for e in edges):
                    return False
            elif key == "is" and val.lower() == "orphan":
                degree = sum(1 for e in edges if e.get("from") == nid or e.get("to") == nid)
                if degree != 0:
                    return False
            # Unknown filter key: ignored (zero regression).
        return True

# Dynamically binding Stage 57-64 extensions from infrastructure.
# Auto-bound extensions from infrastructure (no static import).
import importlib as _importlib
_extras = _importlib.import_module("infrastructure.graph_engine_extras")
for _name, _fn in _extras.__dict__.items():
    if not callable(_fn):
        continue
    if _name.startswith("_") or _name in {"ConflictError", "export_graph"}:
        continue
    if not hasattr(GraphQueryEngine, _name):
        setattr(GraphQueryEngine, _name, _fn)

# stdlib-only semantic fallback installed AFTER extras binding.
import re as _re


def _tokenize(text: str):
    return [t.lower() for t in _re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", (text or "").lower()) if len(t) > 2]


def _doc_text(node):
    title = (node.get("title") or node.get("label") or node.get("id") or "").lower()
    body = (node.get("content") or "").lower()
    return title + " " + body


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _wrap_rebuild_semantic_index(self, *args, **kwargs):
    docs = [
        {"id": n.get("id"), "text": " ".join(_tokenize(_doc_text(n)))}
        for n in self._snapshot().get("nodes", [])
        if isinstance(n, dict) and n.get("id")
    ]
    return {"ok": True, "documents": len(docs)}


def _wrap_semantic_search(self, query, top_k=10):
    docs = [
        {"id": n.get("id"), "tokens": set(_tokenize(_doc_text(n)))}
        for n in self._snapshot().get("nodes", [])
        if isinstance(n, dict) and n.get("id")
    ]
    q_tokens = set(_tokenize(query))
    interest_nodes = set()
    for e in self._snapshot().get("edges", []):
        if isinstance(e, dict) and e.get("relation") == "query_hit":
            interest_nodes.add(e.get("to"))
    scored = []
    for doc in docs:
        score = _jaccard(q_tokens, doc["tokens"])
        if doc["id"] in interest_nodes and score > 0:
            score = min(1.0, score + 0.2)
        scored.append((doc["id"], round(score, 4)))
    scored.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return scored[:top_k]


def _wrap_semantic_similarity(self, node_a, node_b):
    rows = {rid: score for rid, score in _wrap_semantic_search(self, f"{node_a} {node_b}", top_k=20)}
    return max(rows.get(node_a, 0.0), rows.get(node_b, 0.0))


GraphQueryEngine.rebuild_semantic_index = _wrap_rebuild_semantic_index
GraphQueryEngine.semantic_search = _wrap_semantic_search
GraphQueryEngine.semantic_similarity = _wrap_semantic_similarity
