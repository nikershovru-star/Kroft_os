"""Reference knowledge search service (ТЗ-SEARCH-01, ADR-069) — LLM-free, deterministic.

K1-compliant: stdlib + contracts only. STANDALONE read-only service (Флаг C): it is
constructed with an ``ILayeredMemory`` + optional ``IGraphEngine`` and queries them on
demand. It does NOT wire into ``build_kernel`` and the kernel never depends on it (K6).

Design flags honored:
- Флаг A (no per-call index mutation): we PURE-SCAN the memory/graph sources on each
  call. We do NOT write into the shared ``ContentIndex``. Token overlap is computed
  inline over the candidate's own text — deterministic, side-effect free.
- Флаг B (total ranking order): hits are sorted by (confidence.value DESC, relevance
  DESC, id ASC). The id tie-breaker makes repeated queries byte-identical (I-09).
- Флаг D (contract fidelity): ``SearchHit.causal`` is the REAL ``Optional[CausalMark]``
  type. Graph nodes have no confidence/causal, so GRAPH hits use a neutral default
  confidence (0.5) and ``causal=None`` so ranking stays uniform across layers.

O1: read-only — never mutates memory, graph, or contracts.
"""

from __future__ import annotations

import re
from typing import List, Optional

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    ProvenanceType,
)
from contracts.i_cognitive_kernel import ILayeredMemory
from contracts.i_search import ISearchService, SearchHit, SearchScope
from contracts.knowledge_graph import IGraphEngine, Node


_TOKEN_RE = re.compile(r"[a-z0-9_]+")

# Search Quality v0.1 (Product Mode): minimal ranking boosts, no new layer/port.
# A) title match weights more than body match; B) architecture docs (ADR/RFC/KEH/KES/
#    architecture) get a type boost; C) stop-files excluded by name.
_STOP_NAMES = {
    "license", "readme", "makefile", "dockerfile", "__init__", "setup",
    "node_modules", ".git", "changelog", "contributing",
}
_DOC_TYPE_HINT = re.compile(
    r"(adr-|architecture|rfc-|keh|kes|krm|kera|keh\W|architecture adr|obsidian\s*vault)",
    re.IGNORECASE,
)
_TITLE_BOOST = 0.5    # +0.5*title_overlap on top of body overlap
_DOC_TYPE_BOOST = 1.3  # multiplicative boost for architecture-class documents


def _is_stop_file(label: str) -> bool:
    """Exclude utility/root files by bare name (Search Quality v0.1, task C)."""
    base = label.replace("\\", "/").split("/")[-1].lower()
    base = re.sub(r"\.(md|txt|py|rst)$", "", base)
    return base in _STOP_NAMES


def _doc_type_boost(label: str) -> float:
    """Architecture-class documents rank above incidental notes (task B).

    Boost by FILE NAME (not folder/path): a file literally named 'ADR-043 ...'
    is an architecture decision; a note merely *mentioning* 'ADR-043' in its body
    must NOT inherit the boost. Folder 'architecture/...' gets a milder boost
    (everything there is architecture-relevant).
    """
    fname = label.replace("\\", "/").split("/")[-1].lower()
    fname = re.sub(r"\.(md|txt|py|rst)$", "", fname)
    if re.search(r"^(adr-|rfc-)", fname):
        return _DOC_TYPE_BOOST          # explicit decision/request doc
    if _DOC_TYPE_HINT.search(label or ""):
        return 1.15                      # milder boost for architecture-class folders
    return 1.0


def _tokenize(text: str) -> List[str]:
    """Deterministic lowercase tokenization (LLM-free). Short tokens (<2 chars) dropped
    to match ContentIndex semantics and keep matching stable."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2]


class ReferenceSearchService(ISearchService):
    """Deterministic retrieval over semantic/episodic/normative memory + knowledge graph.

    Construction is the ONLY wiring point (Флаг C): pass the memory and (optionally) the
    graph. No build_kernel involvement. The service never writes to either source.
    """
    def __init__(self, memory: ILayeredMemory,
                 graph: Optional[IGraphEngine] = None) -> None:
        self._memory = memory
        self._graph = graph

    # -- ISearchService ----------------------------------------------------
    def search(self, query: str,
               scope: SearchScope = SearchScope.ALL,
               top_k: int = 5) -> List[SearchHit]:
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []  # negative: empty/short-token query -> no hits
        if top_k <= 0:
            return []

        candidates = self._collect(scope, q_tokens)
        if not candidates:
            return []

        # Флаг B: TOTAL order (confidence desc, relevance desc, id asc) -> deterministic
        candidates.sort(key=lambda h: (-h.confidence.value, -h.relevance, h.source))
        return candidates[:top_k]

    # -- internal: pure scan (Флаг A) -------------------------------------
    def _collect(self, scope: SearchScope, q_tokens: List[str]) -> List[SearchHit]:
        hits: List[SearchHit] = []
        want = (
            {scope}
            if scope != SearchScope.ALL
            else {SearchScope.SEMANTIC, SearchScope.EPISODIC,
                  SearchScope.NORMATIVE, SearchScope.GRAPH}
        )
        if scope not in want and scope != SearchScope.ALL:
            return []  # negative: unknown/empty scope -> no hits

        if SearchScope.SEMANTIC in want:
            for f in self._memory.get_semantic():
                hits.extend(self._match_semantic(f, q_tokens))
        if SearchScope.EPISODIC in want:
            for ep in self._memory.get_episodes():
                hits.extend(self._match_episode(ep, q_tokens))
        if SearchScope.NORMATIVE in want:
            for p in self._memory.get_normative():
                hits.extend(self._match_policy(p, q_tokens))
        if SearchScope.GRAPH in want and self._graph is not None:
            for n in self._graph.nodes():
                if _is_stop_file(n.label):
                    continue  # task C: skip utility/root files
                hits.extend(self._match_node(n, q_tokens))
        return hits

    # -- per-entity matching (deterministic token overlap) ----------------
    def _overlap(self, q_tokens: List[str], text: str) -> float:
        c_tokens = _tokenize(text)
        if not c_tokens:
            return 0.0
        c_set = set(c_tokens)
        matched = sum(1 for t in q_tokens if t in c_set)
        # relevance = fraction of query tokens that appear in the candidate
        return matched / len(q_tokens)

    def _match_semantic(self, f, q_tokens) -> List[SearchHit]:
        rel = self._overlap(q_tokens, f.content)
        if rel <= 0.0:
            return []
        return [SearchHit(
            content=f.content,
            source=f"semantic:{f.id}",
            hit_type=SearchScope.SEMANTIC.value,
            confidence=f.confidence,
            causal=getattr(f, "causal", None),
            relevance=rel,
        )]

    def _match_episode(self, ep, q_tokens) -> List[SearchHit]:
        rel = self._overlap(q_tokens, ep.summary)
        if rel <= 0.0:
            return []
        return [SearchHit(
            content=ep.summary,
            source=f"episodic:{ep.id}",
            hit_type=SearchScope.EPISODIC.value,
            confidence=ep.confidence,
            causal=None,  # episodes carry no CausalMark
            relevance=rel,
        )]

    def _match_policy(self, p, q_tokens) -> List[SearchHit]:
        rel = self._overlap(q_tokens, p.body)
        if rel <= 0.0:
            return []
        return [SearchHit(
            content=p.body,
            source=f"normative:{p.id}",
            hit_type=SearchScope.NORMATIVE.value,
            confidence=p.confidence,
            causal=None,  # policies carry no CausalMark
            relevance=rel,
        )]

    def _match_node(self, n: Node, q_tokens) -> List[SearchHit]:
        # graph node text = label + metadata values
        text = n.label + " " + " ".join(str(v) for v in n.metadata.values())
        rel = self._overlap(q_tokens, text)
        if rel <= 0.0:
            return []
        # Search Quality v0.1: title match boosts more than body; doc-type boosts
        # architecture-class docs (ADR/RFC/KEH/KES/architecture) above incidental notes.
        title_rel = self._overlap(q_tokens, n.label)
        boost = (1.0 + _TITLE_BOOST * title_rel) * _doc_type_boost(n.label)
        rel = rel * boost
        # Флаг D: graph nodes have no confidence/causal -> neutral defaults so ranking
        # is uniform with the other (confidence-carrying) layers.
        return [SearchHit(
            content=n.label,
            source=f"graph:{n.id}",
            hit_type=SearchScope.GRAPH.value,
            confidence=ConfidenceScore(0.5, ProvenanceType.AGGREGATION),
            causal=None,
            relevance=rel,
        )]


def build_search_service(memory: ILayeredMemory,
                         graph: Optional[IGraphEngine] = None) -> ReferenceSearchService:
    """Factory: assemble a standalone ``ReferenceSearchService`` (ТЗ-SEARCH-01 commit 3).

    Intentionally SEPARATE from ``build_kernel`` (Флаг C): the cognitive kernel does
    NOT depend on search, and search does NOT mutate the kernel. Callers (a future
    advisor/reasoning context-request TЗ, or an external agent/API) construct the
    service directly from the memory + graph they already hold. The kernel is never
    touched, so the god-factory (Флаг 1 OBS-01) is not aggravated.
    """
    return ReferenceSearchService(memory=memory, graph=graph)
