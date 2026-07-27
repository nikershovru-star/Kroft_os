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
import re
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from contracts import IService, IGraphBuilder, IGraphQuery


# Stage 21: local tokenizer (mirror of ContentIndex._tokenize). Sibling-import
# into services/ is forbidden by the arch gate, so the regex is duplicated
# here rather than imported from content_index.
_TOKEN_RE = re.compile(r"\w+")
_MIN_TOKEN_LEN = 2


def _tokenize(text: str) -> List[str]:
    """\\w+ tokens, lowercased, len >= 2. No stemming / stop-words."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= _MIN_TOKEN_LEN]


# Stage 21: filter syntax `key:value` (value is \S+ up to whitespace).
_FILTER_RE = re.compile(r"\b(\w+):(\S+)\b")


class GraphQueryEngine(IGraphQuery):
    """Pure read-only structural query engine over a shared IGraphBuilder."""

    def __init__(self, graph: IGraphBuilder, index: Optional[Any] = None,
                 semantic_index: Optional[Any] = None,
                 embedding: Optional[Any] = None) -> None:
        # Snapshot-on-read: every query pulls a fresh deep-copy snapshot via
        # graph.get_graph(), so the crawler may mutate the live graph (add
        # nodes/edges) between our calls without corrupting an in-flight query.
        self._graph = graph
        # Stage 18: optional ContentIndex (duck-typed — the services
        # cross-import gate forbids importing the sibling service; the DI
        # composition root wires the SAME instance the crawler writes to).
        # index=None => zero regression: search() returns [].
        self._index = index
        # Stage 29: optional SemanticIndex + IEmbedding (duck-typed pair,
        # same DI convention). Either None => semantic_search() returns [].
        self._semantic_index = semantic_index
        self._embedding = embedding

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

    def path(self, from_id: str, to_id: str, max_depth: int = 10) -> Optional[List[str]]:
        if max_depth < 0:
            return None
        g = self._snapshot()
        # adjacency (directed forward edges only)
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
        # BFS for shortest path
        queue: "deque[str]" = deque([from_id])
        visited = {from_id}
        parent: Dict[str, Optional[str]] = {from_id: None}
        depth = {from_id: 0}
        while queue:
            cur = queue.popleft()
            if cur == to_id:
                # reconstruct
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
        """Split a query into (text_terms, structural_filters).

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
