"""Research Service port (ТЗ-RESEARCH-01, ADR-070).

K1-compliant: stdlib + contracts only. LLM-free by default (I-09), optional LLM synthesis
via ILLMAdvisor with graceful fallback to retrieval-only (lesson from LLM-01/02).

DESIGN (per ТЗ + reviewer flags):
- STANDALONE service (Флаг C SEARCH-01): constructed from an ``ISearchService`` (+ optional
  memory for SOFT write-back, + optional ILLMAdvisor for synthesis). It does NOT wire into
  ``build_kernel`` and the kernel never depends on it (K6). No god-factory aggravation.
- Reuses ISearchService — does NOT duplicate the search port (one-port-per-boundary).
- LLM-free by default: synthesis = deterministic aggregation of top-k findings (no model).
  Optional LLM synthesis via ILLMAdvisor; on LLMError/LLMTimeout -> falls back to the
  retrieval-only report (== result without LLM, I-10 lesson).
- O1: if the service writes back, it writes ONLY SOFT knowledge (commit_semantic). It never
  mutates HARD/FSM/contracts. The reference impl writes under an explicit opt-in guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from contracts.cognitive_domain import CausalMark, ConfidenceScore, Provenance
from contracts.i_search import SearchHit, SearchScope


@dataclass(frozen=True)
class ResearchGoal:
    """A research request (frozen VO — real types, no duck-objects, Флаг LLM-01/SEARCH-01)."""
    query: str
    scope: SearchScope = SearchScope.ALL
    max_findings: int = 5


@dataclass(frozen=True)
class ResearchReport:
    """The synthesized research result (frozen VO)."""
    findings: Tuple[SearchHit, ...]      # retrieved evidence (from ISearchService)
    summary: str                         # deterministic top-finding summary (or LLM synthesis)
    confidence: ConfidenceScore          # aggregated confidence across findings
    causal: Optional[CausalMark]         # carried from the highest-confidence finding (if any)
    provenance: Provenance               # how the report was produced


class IResearchService:
    """Port: deterministic research cycle over accumulated knowledge (ТЗ-RESEARCH-01).

    research(goal) MUST be deterministic (I-09) on the LLM-free path. The same goal against
    the same sources MUST yield an identical report (findings order + summary + confidence).
    """
    def research(self, goal: ResearchGoal) -> ResearchReport:
        raise NotImplementedError
