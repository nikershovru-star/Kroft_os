"""Reference research service (ТЗ-RESEARCH-01, ADR-070) — LLM-free deterministic cycle.

K1-compliant: stdlib + contracts only. STANDALONE, read-first service (Флаг C SEARCH-01):
constructed with an ``ISearchService`` (+ optional memory for SOFT write-back, + optional
ILLMAdvisor for synthesis). Does NOT wire into ``build_kernel``; the kernel never depends on
it (K6). No god-factory aggravation.

Design flags honored:
- LLM-free default (I-09): synthesis = deterministic aggregation of top-k findings. The
  summary is the highest-relevance finding's content (search already total-orders by
  confidence desc, relevance desc, id asc — Флаг B SEARCH-01), so the report is byte-stable
  across identical calls.
- Optional LLM synthesis via ILLMAdvisor: on LLMError/LLMTimeout -> graceful fallback to the
  retrieval-only summary (== result without LLM, lesson LLM-01/02). The fallback path is
  itself deterministic, so determinism holds for the LLM-free result.
- O1: if the service writes back knowledge, it writes ONLY SOFT via ``commit_semantic`` and
  ONLY under an explicit opt-in flag (``write_back=True``). It never touches HARD/FSM/contracts.
- Reuses ISearchService — does NOT duplicate the search port (one-port-per-boundary).
"""

from __future__ import annotations

from statistics import mean
from typing import List, Optional

from contracts.cognitive_domain import (
    CausalMark,
    ConfidenceScore,
    Provenance,
    ProvenanceType,
)
from contracts.i_cognitive_kernel import ILayeredMemory
from contracts.i_llm_advisor import AdviseContext, ILLMAdvisor, LLMError, LLMTimeout
from contracts.i_research import IResearchService, ResearchGoal, ResearchReport
from contracts.i_search import ISearchService, SearchHit


def _research_context(query: str, evidence: str) -> AdviseContext:
    """Build an advisor context for LLM synthesis of a research summary."""
    return AdviseContext(
        intent_text=f"Synthesize a concise research summary for: {query}",
        world_facts=(evidence,),
        candidate_descriptions=(),
    )


class ReferenceResearchService(IResearchService):
    """Deterministic research cycle over accumulated knowledge (ТЗ-RESEARCH-01).

    research(goal) -> ResearchReport:
      1. retrieve findings via ISearchService (reuse, no duplication)
      2. aggregate confidence (mean of finding confidences — deterministic)
      3. synthesize summary (top finding content LLM-free; optional LLM with fallback)
      4. optionally write back a SOFT synthetic fact (opt-in only, O1-guarded)
    """
    def __init__(self, search: ISearchService,
                 memory: Optional[ILayeredMemory] = None,
                 llm_advisor: Optional[ILLMAdvisor] = None,
                 write_back: bool = False) -> None:
        self._search = search
        self._memory = memory
        self._llm_advisor = llm_advisor
        self._write_back = write_back  # O1: explicit opt-in, SOFT-only

    # -- IResearchService --------------------------------------------------
    def research(self, goal: ResearchGoal) -> ResearchReport:
        findings: List[SearchHit] = self._search.search(
            goal.query, scope=goal.scope, top_k=goal.max_findings)

        # negative: empty / no-match -> empty report (deterministic)
        if not findings:
            return ResearchReport(
                findings=(),
                summary="",
                confidence=ConfidenceScore(0.0, ProvenanceType.OBSERVATION),
                causal=None,
                provenance=Provenance(source="research", actor="research-service"),
            )

        # deterministic aggregation (I-09): findings are already total-ordered by search
        conf_values = [h.confidence.value for h in findings]
        agg_conf = ConfidenceScore(mean(conf_values), ProvenanceType.AGGREGATION)
        top = findings[0]
        causal: Optional[CausalMark] = top.causal

        # synthesis: LLM-free default; optional LLM with graceful fallback
        summary, provenance = self._synthesize(goal, findings, top)

        report = ResearchReport(
            findings=tuple(findings),
            summary=summary,
            confidence=agg_conf,
            causal=causal,
            provenance=provenance,
        )

        # O1: write-back is SOFT-only, opt-in, never automatic
        if self._write_back and self._memory is not None:
            self._memory.commit_semantic(self._synthetic_fact(goal, summary, agg_conf, causal))

        return report

    # -- internal ----------------------------------------------------------
    def _synthesize(self, goal: ResearchGoal, findings: List[SearchHit], top: SearchHit):
        """LLM-free summary = top finding content. If an LLM advisor is wired, attempt
        synthesis; on ANY failure fall back to the retrieval-only summary (== no LLM)."""
        base_summary = top.content
        base_prov = Provenance(source="research", actor="research-service")

        if self._llm_advisor is None:
            return base_summary, base_prov

        try:
            evidence = "\n".join(f"- {h.content} ({h.source})" for h in findings)
            advice = self._llm_advisor.advise(_research_context(goal.query, evidence))
            if advice is not None and getattr(advice, "suggestion", ""):
                return advice.suggestion, Provenance(source="llm", actor="research-service")
        except (LLMError, LLMTimeout):
            # graceful fallback == retrieval-only (lesson LLM-01/02)
            pass
        return base_summary, base_prov

    def _synthetic_fact(self, goal, summary, agg_conf, causal):
        from contracts.cognitive_domain import NodeLamportClock, SemanticFact
        clk = NodeLamportClock("research")
        return SemanticFact(
            id=f"sf-research-{abs(hash((goal.query, summary))) % 10**9}",
            content=summary,
            confidence=agg_conf,
            causal=clk.tick(),
            source_episodes=(),
        )


def build_research_service(search: ISearchService,
                           memory: Optional[ILayeredMemory] = None,
                           llm_advisor: Optional[ILLMAdvisor] = None,
                           write_back: bool = False) -> ReferenceResearchService:
    """Factory: assemble a standalone ``ReferenceResearchService`` (ТЗ-RESEARCH-01 commit 3).

    Intentionally SEPARATE from ``build_kernel`` (Флаг C SEARCH-01): the cognitive kernel
    does NOT depend on research, and research does NOT mutate the kernel. Callers (an external
    agent/API/research loop) construct the service directly from an ``ISearchService`` they
    already hold. The kernel is never touched, so the god-factory (Флаг 1 OBS-01) is not
    aggravated. Optional ``llm_advisor`` enables LLM synthesis with graceful fallback to
    retrieval-only; ``write_back=True`` opts into SOFT-only write-back (O1-guarded).
    """
    return ReferenceResearchService(
        search=search, memory=memory, llm_advisor=llm_advisor, write_back=write_back)
