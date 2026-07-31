"""Wave 8 (ADR-011) Phase E — contract tests.

Ports must be abstract; Fact must be frozen with append-only history (LAW 3).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import abc
import dataclasses

import pytest

from contracts.i_knowledge import (
    Entity,
    Fact,
    Hypothesis,
    IEntityExtractor,
    IFactChecker,
    IKnowledgeGraph,
    IValidator,
    IngestReport,
    Relation,
)


# --- ports are abstract ----------------------------------------------------
@pytest.mark.parametrize(
    "port", [IEntityExtractor, IValidator, IFactChecker, IKnowledgeGraph]
)
def test_ports_are_abstract(port):
    assert issubclass(port, abc.ABC)
    assert getattr(port, "__abstractmethods__", None), f"{port.__name__} has no abstract methods"
    with pytest.raises(TypeError):
        port()  # cannot instantiate a port


def test_port_method_names():
    assert "extract" in IEntityExtractor.__abstractmethods__
    assert "extract_relations" in IEntityExtractor.__abstractmethods__
    assert "validate" in IValidator.__abstractmethods__
    assert "check" in IFactChecker.__abstractmethods__
    assert {"add_fact", "facts", "find"} <= set(IKnowledgeGraph.__abstractmethods__)


# --- entities are frozen ---------------------------------------------------
@pytest.mark.parametrize("cls", [Entity, Relation, Hypothesis, Fact])
def test_entities_are_frozen(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


def test_fact_cannot_be_mutated():
    f = Fact(subject="A", predicate="rel", object="B")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.confidence = 0.99


def test_fact_carries_law4_fields():
    """LAW 4: Decision -> Evidence -> Explanation."""
    f = Fact(
        subject="Rust",
        predicate="is",
        object="language",
        source="phi4",
        evidence="raw chunk",
        confidence=0.9,
    )
    assert f.source == "phi4"
    assert f.evidence == "raw chunk"
    assert f.confidence == 0.9
    assert f.history == ()


# --- history is append-only ------------------------------------------------
def test_history_is_tuple_even_when_built_from_list():
    f = Fact(subject="A", predicate="r", object="B", history=[{"action": "x"}])
    assert isinstance(f.history, tuple)


def test_with_history_returns_new_object_and_appends():
    f0 = Fact(subject="A", predicate="r", object="B")
    f1 = f0.with_history("validated", "validator", timestamp=1.0)
    f2 = f1.with_history("stored", "platform", timestamp=2.0)

    assert f0.history == ()                     # original untouched
    assert len(f1.history) == 1
    assert len(f2.history) == 2
    assert f2.history[0]["action"] == "validated"
    assert f2.history[1]["action"] == "stored"
    assert f2.history[1]["actor"] == "platform"
    assert f2.history[0]["timestamp"] == 1.0
    assert f1 is not f2


def test_history_container_rejects_in_place_append():
    f = Fact(subject="A", predicate="r", object="B").with_history("validated", "v")
    with pytest.raises(AttributeError):
        f.history.append({"action": "hack"})


# --- helpers ---------------------------------------------------------------
def test_hypothesis_well_formedness():
    assert Hypothesis(subject="A", predicate="r", object="B").is_well_formed()
    assert not Hypothesis(subject="A", predicate="", object="B").is_well_formed()
    assert not Hypothesis(subject="  ", predicate="r", object="B").is_well_formed()


def test_hypothesis_and_fact_expose_relation():
    h = Hypothesis(subject="A", predicate="r", object="B")
    assert h.as_relation() == Relation("A", "r", "B")
    assert Fact(subject="A", predicate="r", object="B").as_relation() == Relation("A", "r", "B")


def test_fact_key_is_triple():
    assert Fact(subject="A", predicate="r", object="B").key() == ("A", "r", "B")


def test_ingest_report_acceptance_rate():
    r = IngestReport(document_id="d")
    assert r.acceptance_rate == 0.0          # no hypotheses -> no division by zero
    r.hypotheses = 4
    r.accepted = [Fact(subject="A", predicate="r", object="B")]
    assert r.acceptance_rate == 0.25
