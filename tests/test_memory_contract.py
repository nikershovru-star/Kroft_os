"""Wave 9 (ADR-012) Phase F — contract tests.

Ports abstract, MemoryItem frozen with immutable containers (LAW 3).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import abc
import dataclasses

import pytest

from contracts.i_memory import (
    ConsolidationReport,
    IMemoryStore,
    IProceduralMemory,
    ISemanticMemory,
    MemoryItem,
    MemoryKind,
    MemoryQuery,
)


# --- ports -----------------------------------------------------------------
@pytest.mark.parametrize("port", [IMemoryStore, ISemanticMemory, IProceduralMemory])
def test_ports_are_abstract(port):
    assert issubclass(port, abc.ABC)
    assert getattr(port, "__abstractmethods__", None), f"{port.__name__} has no abstract methods"
    with pytest.raises(TypeError):
        port()


def test_port_method_names():
    assert {"put", "get", "query", "delete_expired", "compress"} <= set(
        IMemoryStore.__abstractmethods__
    )
    assert "search" in ISemanticMemory.__abstractmethods__
    assert {"record_procedure", "recall_procedure"} <= set(
        IProceduralMemory.__abstractmethods__
    )


def test_partial_implementation_cannot_instantiate():
    class Half(IMemoryStore):
        def put(self, item): ...
        def get(self, key): ...
    with pytest.raises(TypeError):
        Half()


# --- MemoryItem immutability ----------------------------------------------
def test_memory_item_is_frozen():
    assert dataclasses.is_dataclass(MemoryItem)
    assert MemoryItem.__dataclass_params__.frozen is True
    item = MemoryItem(key="k", content="c")
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.content = "hacked"


def test_tags_normalised_to_tuple_even_from_list():
    item = MemoryItem(key="k", content="c", tags=["a", "b"])
    assert isinstance(item.tags, tuple)
    with pytest.raises(AttributeError):
        item.tags.append("c")


def test_embedding_normalised_to_tuple():
    item = MemoryItem(key="k", content="c", embedding=[0.1, 0.2])
    assert isinstance(item.embedding, tuple)
    assert MemoryItem(key="k", content="c").embedding is None


def test_timestamp_autofilled():
    assert MemoryItem(key="k", content="c").timestamp > 0
    assert MemoryItem(key="k", content="c", timestamp=42.0).timestamp == 42.0


def test_with_tags_returns_new_object_no_duplicates():
    a = MemoryItem(key="k", content="c", tags=("x",))
    b = a.with_tags("y", "x")
    assert a.tags == ("x",)               # original untouched
    assert b.tags == ("x", "y")           # deduplicated, order preserved
    assert a is not b


def test_with_importance_is_immutable_update():
    a = MemoryItem(key="k", content="c", importance=1.0)
    b = a.with_importance(0.2)
    assert a.importance == 1.0 and b.importance == 0.2


# --- TTL semantics ---------------------------------------------------------
def test_ttl_none_never_expires():
    assert MemoryItem(key="k", content="c", timestamp=0.0, ttl=None).is_expired(1e9) is False


def test_ttl_expiry_boundary():
    item = MemoryItem(key="k", content="c", timestamp=100.0, ttl=10)
    assert item.is_expired(109.0) is False
    assert item.is_expired(110.0) is False      # exactly at the edge: still alive
    assert item.is_expired(110.1) is True


def test_age_never_negative():
    assert MemoryItem(key="k", content="c", timestamp=100.0).age(50.0) == 0.0


def test_has_tags_uses_and_semantics():
    item = MemoryItem(key="k", content="c", tags=("a", "b"))
    assert item.has_tags(["a"]) and item.has_tags(["a", "b"])
    assert not item.has_tags(["a", "z"])
    assert item.has_tags([])


# --- query / taxonomy ------------------------------------------------------
def test_memory_query_defaults_are_not_shared():
    q1, q2 = MemoryQuery(), MemoryQuery()
    q1.tags.append("x")
    assert q2.tags == []                  # default_factory, not a shared list


def test_memory_kind_taxonomy():
    assert MemoryKind.SESSION in MemoryKind.ALL
    assert len(set(MemoryKind.ALL)) == len(MemoryKind.ALL)


def test_consolidation_report_rate():
    r = ConsolidationReport(session_key="s")
    assert r.promotion_rate == 0.0        # no division by zero
    r.examined = 4
    r.promoted = [MemoryItem(key="k", content="c")]
    assert r.promotion_rate == 0.25
