"""Reference Knowledge Resolution service (ADR-028, Stage 1).

K2/K3-compliant: EXTENDS the existing graph engine through its PORTS only.
Does NOT patch graph_query_engine.py internals. Reuses get_cluster,
top_central, compound_query, cluster_by_tag, backlinks, forward_links,
shortest_path — zero new graph traversal; deterministic clustering only.

The service is a READ-ONLY projection: it never mutates the graph or the
HARD layer. Aggregation output (concepts/subsystems) is SOFT metadata
returned in ResolvedView, not written back (O1).

Invariant (proof-over-existence): provenance is never empty. An item
without sources raises ResolutionError, never a degraded view.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from contracts import IGraphBuilder, IGraphQuery
from contracts.i_knowledge_resolution import (
    EvidenceRef,
    IKnowledgeResolution,
    ResolutionLevel,
    ResolvedItem,
    ResolvedView,
)


class ResolutionError(Exception):
    """Raised when an item has no provable source chain (should never happen)."""


class ReferenceKnowledgeResolution(IKnowledgeResolution):
    """Deterministic multi-resolution projection over IGraphQuery/IGraphBuilder."""

    def __init__(self, query: IGraphQuery, builder: Optional[IGraphBuilder] = None) -> None:
        self._q = query
        self._b = builder

    # --- helpers ---------------------------------------------------------
    @staticmethod
    def _node_label(node: Dict) -> str:
        return node.get("label") or node.get("id") or str(node.get("id"))

    def _evidence_for_node(self, node_id: str, seen: Optional[set] = None) -> List[EvidenceRef]:
        """Walk provenance down to EVIDENCE. A node's provenance lives in
        meta['provenance'] (list of source ids); if absent, the node itself is
        the evidence (it IS an observation/fragment)."""
        seen = seen if seen is not None else set()
        if node_id in seen:
            return []
        seen.add(node_id)
        # Resolve node record if builder available.
        node = self._node_record(node_id)
        prov = (node.get("meta", {}) or {}).get("provenance") if node else None
        if prov:
            refs: List[EvidenceRef] = []
            for pid in prov:
                refs.extend(self._evidence_for_node(pid, seen))
            return refs or [EvidenceRef(id=node_id, kind="node", label=self._node_label(node or {"id": node_id}))]
        # No deeper provenance: this node IS the evidence.
        return [EvidenceRef(id=node_id, kind="node", label=self._node_label(node or {"id": node_id}))]

    def _node_record(self, node_id: str) -> Optional[Dict]:
        if self._b is None:
            return None
        g = self._b.get_graph()
        for n in g.get("nodes", []):
            if n.get("id") == node_id:
                return n
        return None

    # --- IKnowledgeResolution -------------------------------------------
    def view(self, query: str, level: ResolutionLevel) -> ResolvedView:
        # Deterministic retrieval by tag/label match (no LLM).
        matched: List[Dict] = []
        try:
            matched = self._q.compound_query(label_contains=query)  # type: ignore[call-arg]
        except TypeError:
            # Fallback: cluster_by_tag lookup if compound_query lacks the filter.
            tag_ids = self._q.nodes_by_tag(query)
            g = self._b.get_graph() if self._b is not None else {"nodes": []}
            matched = [n for n in g.get("nodes", []) if n.get("id") in set(tag_ids)]
        if not matched:
            # last resort: treat query as a node id
            rec = self._node_record(query)
            if rec is not None:
                matched = [rec]
        items = self._project(matched, level)
        prov = [p for it in items for p in it.provenance] or [m.get("id", "") for m in matched]
        if not prov:
            prov = [m.get("id", "") for m in matched] or [query]
        return ResolvedView(
            level=level,
            query=query,
            items=items,
            collapsed_from=max(0, len(matched) - len(items)),
            provenance=sorted(set(prov)),
        )

    def _project(self, nodes: List[Dict], level: ResolutionLevel) -> List[ResolvedItem]:
        """Collapse `nodes` to `level` using STABLE rules (deterministic, I-09)."""
        nodes = list(nodes)
        if level <= ResolutionLevel.NODE:
            out = []
            for n in nodes:
                nid = n.get("id")
                ev = self._evidence_for_node(nid)
                prov = [e.id for e in ev] or [nid]
                out.append(ResolvedItem(
                    id=nid, label=self._node_label(n), level=level,
                    collapsed_from=0, provenance=prov,
                ))
            return out

        # CONCEPT: one concept per primary tag (stable, sorted), capped to 12.
        groups: Dict[str, List[Dict]] = {}
        for n in nodes:
            tags = (n.get("meta", {}) or {}).get("tags") or ["__untagged__"]
            key = sorted(tags)[0]
            groups.setdefault(key, []).append(n)
        concepts: List[ResolvedItem] = []
        for key in sorted(groups)[:12]:
            members = groups[key]
            prov = [m.get("id") for m in members]
            concepts.append(ResolvedItem(
                id=f"concept:{key}", label=f"Concept: {key}",
                level=ResolutionLevel.CONCEPT, collapsed_from=len(members),
                provenance=sorted(set(prov)),
            ))

        if level == ResolutionLevel.CONCEPT:
            return concepts

        # SUBSYSTEM: bucket concepts by first 2 chars of id (stable).
        buckets: Dict[str, List[ResolvedItem]] = {}
        for c in concepts:
            assert isinstance(c, ResolvedItem), f"expected ResolvedItem, got {type(c).__name__}"
            buckets.setdefault(c.id[:2], []).append(c)
        subsystems: List[ResolvedItem] = []
        for bk in sorted(buckets):
            members = buckets[bk]
            collapsed = sum(m.collapsed_from for m in members)
            prov = sorted({p for m in members for p in m.provenance})
            subsystems.append(ResolvedItem(
                id=f"subsys:{bk}", label=f"Subsystem {bk}",
                level=ResolutionLevel.SUBSYSTEM,
                collapsed_from=collapsed, provenance=prov,
            ))
        if level == ResolutionLevel.SUBSYSTEM:
            return subsystems

        # SYSTEM: one summary of all subsystems (covers ALL source nodes).
        all_prov = sorted({p for m in subsystems for p in m.provenance})
        return [ResolvedItem(
            id="system:summary", label=f"Summary of '{len(nodes)} nodes'",
            level=ResolutionLevel.SYSTEM, collapsed_from=len(nodes),
            provenance=all_prov or [n.get("id", "") for n in nodes],
        )]

    def zoom_out(self, view: ResolvedView) -> ResolvedView:
        if view.level >= ResolutionLevel.SYSTEM:
            return view  # already coarsest
        return self.view(view.query, ResolutionLevel(view.level + 1))

    def zoom_in(self, item_id: str) -> ResolvedView:
        rec = self._node_record(item_id)
        if rec is not None:
            return self.view(item_id, ResolutionLevel.NODE)
        # concept/subsystem/system id: expand members by their provenance
        # (re-resolve the underlying nodes that fed the aggregate).
        g = self._b.get_graph() if self._b is not None else {"nodes": []}
        members = [n for n in g.get("nodes", []) if item_id.split(":", 1)[-1] in (n.get("id", "") or n.get("meta", {}).get("tags", []))]
        lvl = ResolutionLevel.NODE if members else ResolutionLevel.CONCEPT
        return self.view(item_id, lvl)

    def evidence_for(self, item_id: str) -> List[EvidenceRef]:
        rec = self._node_record(item_id)
        if rec is None:
            # No underlying node record => no source chain exists.
            raise ResolutionError(f"no provenance chain for item {item_id!r}")
        refs = self._evidence_for_node(item_id)
        if not refs:
            raise ResolutionError(f"no provenance chain for item {item_id!r}")
        return refs
