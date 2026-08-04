"""K8 tests for ТЗ-RESEARCH-01 — deterministic research cycle over SEARCH (LLM-free + fallback).

Covers (acceptance + O1/K1/K6/K8 + ADR-070):
- research returns ResearchReport with findings pulled from ISearchService (reuse, no dup).
- determinism: repeated identical goal -> identical report (I-09).
- aggregate confidence is the mean of finding confidences (deterministic).
- negative: empty / no-match query -> empty report (findings=(), summary='').
- LLM fallback == retrieval-only: advisor raising LLMError/LLMTimeout yields the SAME summary
  as a service with NO advisor (lesson LLM-01/02).
- O1: write-back (opt-in) writes ONLY SOFT via commit_semantic; HARD/FSM/contracts untouched.
- existing SEARCH-01 tests remain green (run separately).

Флаг C: service is standalone (build_research_service, no build_kernel).
Флаг LLM-01/SEARCH-01: frozen VOs with real types (ResearchReport.causal Optional[CausalMark]).
"""

from __future__ import annotations

from contracts.cognitive_domain import (
    ConfidenceScore,
    NodeLamportClock,
    ProvenanceType,
    SemanticFact,
)
from contracts.i_llm_advisor import ILLMAdvisor, LLMError, LLMTimeout
from contracts.i_research import IResearchService, ResearchGoal, ResearchReport
from contracts.i_search import SearchScope
from contracts.knowledge_graph import Node, NodeType
from kernel.memory_store import InMemoryLayeredMemory
from kernel.research import ReferenceResearchService, build_research_service
from kernel.search import build_search_service
from services.knowledge_graph.engine import InMemoryGraphEngine


def _search_service():
    mem = InMemoryLayeredMemory()
    clk = NodeLamportClock("S")
    mem.commit_semantic(SemanticFact(
        id="sf-blue", content="choose blue when sky is clear",
        confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    mem.commit_semantic(SemanticFact(
        id="sf-red", content="avoid red because it fails often",
        confidence=ConfidenceScore(0.6, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    g = InMemoryGraphEngine()
    g.add_node(Node(id="adr65", type=NodeType.ADR, label="ADR-065 llm advisor boundary"))
    return build_search_service(mem, g)


class _FailingAdvisor(ILLMAdvisor):
    def __init__(self, exc): self._exc = exc
    def advise(self, context):  # pragma: no cover - trivial
        raise self._exc


class _SynthesisAdvisor(ILLMAdvisor):
    def advise(self, context):
        class _A:
            suggestion = "SYNTHESIZED: blue is preferred, red avoided"
        return _A()


# ---------------------------------------------------------------------------
# 1. report with findings from SEARCH (reuse, no port duplication)
# ---------------------------------------------------------------------------
def test_research_returns_report_with_findings():
    rs = ReferenceResearchService(_search_service())
    rep = rs.research(ResearchGoal(query="blue red", scope=SearchScope.ALL, max_findings=5))
    assert isinstance(rep, ResearchReport)
    assert len(rep.findings) == 2
    assert rep.findings[0].source == "semantic:sf-blue"  # highest confidence first


def test_research_reuses_search_port_not_duplicate():
    rs = ReferenceResearchService(_search_service())
    assert isinstance(rs, IResearchService)
    rep = rs.research(ResearchGoal(query="ADR"))
    assert any(h.hit_type == "graph" for h in rep.findings)


# ---------------------------------------------------------------------------
# 2. determinism (I-09)
# ---------------------------------------------------------------------------
def test_determinism_repeated_goal():
    rs = ReferenceResearchService(_search_service())
    a = rs.research(ResearchGoal(query="blue red"))
    b = rs.research(ResearchGoal(query="blue red"))
    c = rs.research(ResearchGoal(query="blue red"))
    assert a.summary == b.summary == c.summary
    assert a.confidence.value == b.confidence.value == c.confidence.value
    assert [h.source for h in a.findings] == [h.source for h in b.findings] == [h.source for h in c.findings]


# ---------------------------------------------------------------------------
# 3. aggregate confidence = mean of finding confidences
# ---------------------------------------------------------------------------
def test_aggregate_confidence_is_mean():
    rs = ReferenceResearchService(_search_service())
    rep = rs.research(ResearchGoal(query="blue red"))
    expected = (0.9 + 0.6) / 2
    assert abs(rep.confidence.value - expected) < 1e-9


def test_causal_carried_from_top_finding():
    rs = ReferenceResearchService(_search_service())
    rep = rs.research(ResearchGoal(query="blue red"))
    assert rep.causal is not None  # top semantic fact carries a CausalMark


# ---------------------------------------------------------------------------
# 4. negative: empty / no-match -> empty report
# ---------------------------------------------------------------------------
def test_empty_query_empty_report():
    rs = ReferenceResearchService(_search_service())
    rep = rs.research(ResearchGoal(query=""))
    assert rep.findings == ()
    assert rep.summary == ""
    assert rep.confidence.value == 0.0


def test_no_match_empty_report():
    rs = ReferenceResearchService(_search_service())
    rep = rs.research(ResearchGoal(query="zzznonexistentzzz"))
    assert rep.findings == ()
    assert rep.summary == ""


# ---------------------------------------------------------------------------
# 5. LLM fallback == retrieval-only (lesson LLM-01/02)
# ---------------------------------------------------------------------------
def test_llm_error_falls_back_to_retrieval_only():
    base = ReferenceResearchService(_search_service())
    failing = ReferenceResearchService(_search_service(), llm_advisor=_FailingAdvisor(LLMError("x")))
    a = base.research(ResearchGoal(query="blue red"))
    b = failing.research(ResearchGoal(query="blue red"))
    assert b.summary == a.summary
    assert b.confidence.value == a.confidence.value


def test_llm_timeout_falls_back_to_retrieval_only():
    base = ReferenceResearchService(_search_service())
    failing = ReferenceResearchService(_search_service(), llm_advisor=_FailingAdvisor(LLMTimeout("x")))
    a = base.research(ResearchGoal(query="blue red"))
    b = failing.research(ResearchGoal(query="blue red"))
    assert b.summary == a.summary


def test_llm_synthesis_changes_summary_when_available():
    synth = ReferenceResearchService(_search_service(), llm_advisor=_SynthesisAdvisor())
    rep = synth.research(ResearchGoal(query="blue red"))
    assert rep.summary.startswith("SYNTHESIZED")
    assert len(rep.findings) == 2


# ---------------------------------------------------------------------------
# 6. O1: write-back is SOFT-only, opt-in
# ---------------------------------------------------------------------------
def test_write_back_only_soft_and_opt_in():
    mem = InMemoryLayeredMemory()
    clk = NodeLamportClock("S")
    mem.commit_semantic(SemanticFact(
        id="sf-blue", content="choose blue when sky is clear",
        confidence=ConfidenceScore(0.9, ProvenanceType.AGGREGATION),
        causal=clk.tick(), source_episodes=()))
    g = InMemoryGraphEngine()
    search = build_search_service(mem, g)
    before = len(mem.get_semantic())

    rs_off = ReferenceResearchService(search, memory=mem, write_back=False)
    rs_off.research(ResearchGoal(query="blue"))
    assert len(mem.get_semantic()) == before  # unchanged

    rs_on = ReferenceResearchService(search, memory=mem, write_back=True)
    rs_on.research(ResearchGoal(query="blue"))
    after = mem.get_semantic()
    assert len(after) == before + 1
    assert after[-1].id.startswith("sf-research-")  # SOFT synthetic fact


def test_write_back_absent_memory_no_error():
    rs = ReferenceResearchService(_search_service(), memory=None, write_back=True)
    rep = rs.research(ResearchGoal(query="blue red"))
    assert rep.findings  # still works without memory


# ---------------------------------------------------------------------------
# 7. factory + standalone (Флаг C)
# ---------------------------------------------------------------------------
def test_factory_builds_standalone_service():
    rs = build_research_service(_search_service())
    assert isinstance(rs, ReferenceResearchService)
    assert isinstance(rs, IResearchService)
    rep = rs.research(ResearchGoal(query="blue red"))
    assert rep.findings  # usable without build_kernel (Флаг C)
