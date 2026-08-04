"""Knowledge Search / Retrieval port (ТЗ-SEARCH-01, ADR-069).

K1-compliant: stdlib + contracts only. LLM-free, deterministic (I-09).

DESIGN (per ТЗ + reviewer flags):
- This is a READ-ONLY retrieval port. It does NOT own or duplicate any index
  (content_index / knowledge graph / ILayeredMemory). It scans the existing
  sources on each call (Флаг A: no shared-index mutation per request).
- Ranking is a TOTAL order: (confidence desc, relevance desc, id asc) — the id
  tie-breaker is mandatory for determinism (Флаг B, I-09).
- The service is STANDALONE: constructed with memory + graph, no build_kernel
  wiring (Флаг C). The kernel does NOT depend on search.
- SearchHit carries REAL types, not duck-objects (Флаг D / LLM-01 Флаг 1):
  ``causal: Optional[CausalMark]``. Graph nodes lack confidence/causal, so the
  GRAPH scope uses default confidence/relevance to keep ranking uniform.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from contracts.cognitive_domain import CausalMark, ConfidenceScore


class SearchScope(str, Enum):
    """Which knowledge layer(s) to search. ALL searches every layer."""
    SEMANTIC = "semantic"      # consolidated SOFT semantic facts (ILayeredMemory)
    EPISODIC = "episodic"      # raw recorded experiences (ILayeredMemory)
    NORMATIVE = "normative"    # soft/hard policies (ILayeredMemory)
    GRAPH = "graph"            # knowledge graph nodes
    ALL = "all"


@dataclass(frozen=True)
class SearchHit:
    """A single retrieved knowledge item (frozen VO, K1-clean — no duck-objects).

    ``causal`` is the REAL ``CausalMark`` type when available (semantic/episodic);
    ``None`` for graph nodes (which carry no causal mark — Флаг D).
    """
    content: str
    source: str            # human-readable origin, e.g. "semantic:sf-123" / "graph:adr-7"
    hit_type: str          # SearchScope value that produced this hit
    confidence: ConfidenceScore
    causal: Optional[CausalMark]
    relevance: float       # 0..1 query-match strength (token overlap ratio)


class ISearchService:
    """Port: deterministic retrieval over accumulated knowledge (ТЗ-SEARCH-01).

    Implementations MUST be read-only: they never mutate memory, the graph, or
    contracts (O1). The same ``(query, scope, top_k)`` MUST yield an identical
    ordered list (I-09 determinism).
    """
    def search(self, query: str,
               scope: SearchScope = SearchScope.ALL,
               top_k: int = 5) -> List[SearchHit]:
        raise NotImplementedError
