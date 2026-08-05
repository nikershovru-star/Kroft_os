"""Wave 8 (ADR-011) Phase E — KnowledgePlatform unit tests with mocks.

Mocks: LLM returns JSON entities, Validator accepts/blocks, Fact reaches Graph.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from contracts.i_eval import Scorecard
from contracts.i_knowledge import Fact, Hypothesis
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_policy import PolicyContext
from adapters.graph_knowledge_store import GraphKnowledgeStore
from adapters.llm_entity_extractor import LLMEntityExtractor, _extract_json_array
from services.knowledge_platform import (
    HeuristicFactChecker,
    HeuristicValidator,
    KnowledgePlatform,
    chunk_document,
)

CTX = PolicyContext(query=ModelQuery(task="entity_extraction", prompt=""))

TRIPLES = [
    {"subject": "Rust", "predicate": "is", "object": "systems language"},
    {"subject": "Rust", "predicate": "has", "object": "borrow checker"},
]


class _FakeGraphBuilder:
    """Structural stand-in for InMemoryGraphBuilder."""

    def __init__(self):
        self.nodes = {}
        self.edges = []

    def add_node(self, id, label, meta):
        self.nodes[id] = {"id": id, "label": label, "meta": meta}

    def add_edge(self, from_id, to_id, relation):
        for e in self.edges:
            if e["from"] == from_id and e["to"] == to_id:
                return
        self.edges.append({"from": from_id, "to": to_id, "relation": relation})

    def get_graph(self):
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges)}


def _router_returning(payload, *, error=None, model="phi4"):
    """Build a router callable. NEVER pass ok= (it is a METHOD on LlmResponse)."""
    calls = []

    def _router(query: ModelQuery) -> LlmResponse:
        calls.append(query)
        return LlmResponse(
            text=payload,
            model=model,
            actual_model=model,
            trace_id="trace-42",
            error=error,
        )

    _router.calls = calls
    return _router


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------
def test_chunk_document_splits_on_blank_lines():
    assert chunk_document("a\n\nb\n\n\n c ") == ["a", "b", "c"]
    assert chunk_document("") == []
    assert chunk_document("   ") == []


# --------------------------------------------------------------------------
# extractor
# --------------------------------------------------------------------------
def test_extractor_calls_router_with_reasoning_and_json_mode():
    router = _router_returning(json.dumps(TRIPLES))
    ex = LLMEntityExtractor(router)
    ex.extract_relations("Rust is a systems language.", CTX)
    q = router.calls[0]
    assert q.reasoning is True
    assert q.json_mode is True
    assert q.task == "entity_extraction"
    assert "Rust is a systems language." in q.prompt


def test_extractor_returns_hypotheses_not_facts():
    router = _router_returning(json.dumps(TRIPLES))
    hyps = LLMEntityExtractor(router).extract_relations("text", CTX)
    assert len(hyps) == 2
    assert all(isinstance(h, Hypothesis) for h in hyps)
    assert all(not isinstance(h, Fact) for h in hyps)
    assert hyps[0].source == "phi4"
    assert hyps[0].evidence == "trace-42"
    assert hyps[0].confidence == 0.0        # unknown before Evaluation


def test_extractor_parses_fenced_json():
    router = _router_returning("Вот результат:\n```json\n" + json.dumps(TRIPLES) + "\n```")
    assert len(LLMEntityExtractor(router).extract_relations("t", CTX)) == 2


def test_extractor_survives_garbage_and_errors():
    assert LLMEntityExtractor(_router_returning("not json at all")).extract_relations("t", CTX) == []
    assert LLMEntityExtractor(_router_returning("", error="boom")).extract_relations("t", CTX) == []


def test_extractor_drops_malformed_triples():
    payload = json.dumps([{"subject": "A", "predicate": "", "object": "B"},
                          {"subject": "A", "predicate": "r", "object": "B"}])
    hyps = LLMEntityExtractor(_router_returning(payload)).extract_relations("t", CTX)
    assert len(hyps) == 1


def test_extract_entities_from_triple_slots():
    ents = LLMEntityExtractor(_router_returning(json.dumps(TRIPLES))).extract("t", CTX)
    names = {e.name for e in ents}
    assert names == {"Rust", "systems language", "borrow checker"}
    assert all(e.source == "phi4" for e in ents)


def test_json_array_recovery_variants():
    assert _extract_json_array('[{"subject":"a"}]') == [{"subject": "a"}]
    assert _extract_json_array('{"relations": [{"subject":"a"}]}') == [{"subject": "a"}]
    assert _extract_json_array("nope") == []


# --------------------------------------------------------------------------
# validator / fact checker
# --------------------------------------------------------------------------
def test_checker_prefers_measured_accuracy_over_prior():
    h = Hypothesis(subject="A", predicate="r", object="B")
    sc = Scorecard(task_id="t", model_id="phi4", output="", metrics={"accuracy": 0.35})
    assert HeuristicFactChecker().check(h, sc) == 0.35
    assert HeuristicFactChecker().check(h, None) == 0.8
    assert HeuristicFactChecker().check(Hypothesis(subject="", predicate="r", object="B"), sc) == 0.0


def test_validator_blocks_low_confidence_and_malformed():
    v = HeuristicValidator(min_confidence=0.5)
    low = Scorecard(task_id="t", model_id="m", output="", metrics={"accuracy": 0.2})
    assert v.validate(Hypothesis(subject="A", predicate="r", object="B"), low) is None
    assert v.validate(Hypothesis(subject="A", predicate="", object="B"), None) is None


def test_validator_produces_fact_with_provenance_and_history():
    v = HeuristicValidator(min_confidence=0.5)
    h = Hypothesis(subject="A", predicate="r", object="B", source="phi4", evidence="chunk")
    sc = Scorecard(task_id="t", model_id="phi4", output="", metrics={"accuracy": 0.9},
                   evidence="acc=0.90")
    fact = v.validate(h, sc)
    assert isinstance(fact, Fact)
    assert fact.confidence == 0.9
    assert fact.source == "phi4"
    assert "chunk" in fact.evidence and "acc=0.90" in fact.evidence
    assert fact.history[0]["action"] == "validated"


# --------------------------------------------------------------------------
# platform: hypothesis -> validation -> graph
# --------------------------------------------------------------------------
def _platform(payload, *, scorer=None, min_confidence=0.7, error=None):
    builder = _FakeGraphBuilder()
    store = GraphKnowledgeStore(builder)
    plat = KnowledgePlatform(
        extractor=LLMEntityExtractor(_router_returning(payload, error=error)),
        validator=HeuristicValidator(min_confidence=0.5),
        graph=store,
        scorer=scorer,
        min_confidence=min_confidence,
    )
    return plat, store, builder


def test_platform_writes_verified_facts_to_graph():
    plat, store, builder = _platform(json.dumps(TRIPLES))
    report = plat.ingest("Rust is a systems language.\n\nIt has a borrow checker.", "doc-1")

    assert report.chunks == 2
    assert report.hypotheses == 4              # 2 triples per chunk
    assert len(store.facts()) == 2             # deduplicated by triple key
    f = store.find(subject="Rust", predicate="is")[0]
    assert f.confidence == 0.8                 # structural prior, no scorer
    assert "doc-1" in f.source
    assert [h["action"] for h in f.history] == ["validated", "stored"]
    assert builder.edges                        # underlying graph really got the edge
    assert builder.nodes["Rust"]["meta"]["confidence"] == 0.8


def test_platform_rejects_below_threshold_hypotheses():
    low = Scorecard(task_id="t", model_id="phi4", output="", metrics={"accuracy": 0.55})
    plat, store, _ = _platform(json.dumps(TRIPLES), scorer=lambda h: low, min_confidence=0.7)
    report = plat.ingest("Rust is a systems language.", "doc-2")

    assert store.facts() == []                 # nothing verified => nothing stored
    assert len(report.rejected) == 2
    assert any("rejected (confidence 0.55" in line for line in report.audit_log)


def test_platform_accepts_high_confidence_from_evaluation():
    high = Scorecard(task_id="t", model_id="phi4", output="", metrics={"accuracy": 0.95})
    plat, store, _ = _platform(json.dumps(TRIPLES), scorer=lambda h: high)
    plat.ingest("Rust is a systems language.", "doc-3")
    assert len(store.facts()) == 2
    assert all(f.confidence == 0.95 for f in store.facts())


def test_platform_handles_extraction_failure():
    plat, store, _ = _platform("", error="gateway down")
    report = plat.ingest("some text", "doc-4")
    assert report.hypotheses == 0
    assert store.facts() == []


def test_report_records_acceptance_rate_law5():
    plat, _, _ = _platform(json.dumps(TRIPLES))
    report = plat.ingest("a\n\nb", "doc-5")
    assert report.acceptance_rate > 0
    assert any(line.startswith("summary:") for line in report.audit_log)


# --------------------------------------------------------------------------
# graph store
# --------------------------------------------------------------------------
def test_store_deduplicates_and_finds():
    store = GraphKnowledgeStore(_FakeGraphBuilder())
    f = Fact(subject="A", predicate="r", object="B", confidence=0.9)
    assert store.add_fact(f) is True
    assert store.add_fact(f) is False
    assert store.find(subject="A") == [f]
    assert store.find(predicate="nope") == []
    assert store.graph_snapshot()["edges"][0]["relation"] == "r"
