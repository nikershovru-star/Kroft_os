"""Wave 9 (ADR-012) Phase F — InMemoryMemoryStore: TTL, compression, query."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

from contracts.i_memory import MemoryItem, MemoryKind, MemoryQuery
from adapters.in_memory_memory_store import InMemoryMemoryStore


def _store(*items):
    s = InMemoryMemoryStore()
    for i in items:
        s.put(i)
    return s


def _item(key, content="c", **kw):
    return MemoryItem(key=key, content=content, **kw)


# --- basics ----------------------------------------------------------------
def test_put_get_roundtrip():
    s = _store(_item("a", "hello"))
    assert s.get("a").content == "hello"
    assert s.get("missing") is None


def test_put_overwrites_same_key():
    s = _store(_item("a", "v1"), _item("a", "v2"))
    assert s.get("a").content == "v2"
    assert len(s) == 1


# --- TTL: lazy invisibility, explicit deletion -----------------------------
def test_expired_item_is_invisible_but_still_present_until_cleanup():
    past = time.time() - 100
    s = _store(_item("gone", timestamp=past, ttl=1))
    assert s.get("gone") is None            # invisible immediately
    assert len(s) == 1                      # but not yet physically removed
    assert s.delete_expired() == 1          # explicit cleanup removes it
    assert len(s) == 0


def test_delete_expired_keeps_live_items():
    now = time.time()
    s = _store(
        _item("old", timestamp=now - 100, ttl=1),
        _item("fresh", timestamp=now, ttl=1000),
        _item("eternal", timestamp=now - 1e6, ttl=None),
    )
    assert s.delete_expired() == 1
    assert set(s.keys()) == {"fresh", "eternal"}


def test_delete_expired_is_idempotent():
    s = _store(_item("old", timestamp=time.time() - 100, ttl=1))
    assert s.delete_expired() == 1
    assert s.delete_expired() == 0


def test_query_hides_expired():
    s = _store(
        _item("old", timestamp=time.time() - 100, ttl=1, tags=("t",)),
        _item("new", tags=("t",)),
    )
    assert [i.key for i in s.query(MemoryQuery(tags=["t"]))] == ["new"]


# --- compression (LAW 5: it counts) ----------------------------------------
def test_compress_drops_low_importance_and_counts():
    s = _store(
        _item("keep", importance=0.9),
        _item("keep2", importance=0.3),      # == threshold -> kept
        _item("drop", importance=0.1),
    )
    assert s.compress(threshold=0.3) == 1
    assert set(s.keys()) == {"keep", "keep2"}
    assert s.stats["compressed"] == 1


def test_compress_zero_threshold_drops_nothing():
    s = _store(_item("a", importance=0.0))
    assert s.compress(threshold=0.0) == 0


def test_compress_high_threshold_clears_all():
    s = _store(_item("a", importance=0.5), _item("b", importance=0.9))
    assert s.compress(threshold=1.0) == 2
    assert len(s) == 0


# --- query criteria --------------------------------------------------------
def test_query_by_key_glob_pattern():
    s = _store(_item("session:1:001"), _item("session:1:002"), _item("working:x"))
    got = {i.key for i in s.query(MemoryQuery(key_pattern="session:1:*"))}
    assert got == {"session:1:001", "session:1:002"}


def test_query_tags_are_and_not_or():
    s = _store(
        _item("both", tags=("session", "role:user")),
        _item("one", tags=("session",)),
    )
    assert [i.key for i in s.query(MemoryQuery(tags=["session", "role:user"]))] == ["both"]


def test_query_min_importance():
    s = _store(_item("hi", importance=0.9), _item("lo", importance=0.2))
    assert [i.key for i in s.query(MemoryQuery(min_importance=0.5))] == ["hi"]


def test_query_time_range_is_inclusive():
    s = _store(_item("a", timestamp=100.0), _item("b", timestamp=200.0), _item("c", timestamp=300.0))
    got = {i.key for i in s.query(MemoryQuery(time_range=(100.0, 200.0)))}
    assert got == {"a", "b"}


def test_query_semantic_substring_fallback():
    s = _store(_item("a", "Rust is fast"), _item("b", "Python is slow"))
    assert [i.key for i in s.query(MemoryQuery(semantic_query="rust"))] == ["a"]


def test_query_results_are_newest_first_and_limited():
    s = _store(
        _item("old", timestamp=100.0),
        _item("mid", timestamp=200.0),
        _item("new", timestamp=300.0),
    )
    assert [i.key for i in s.query(MemoryQuery())] == ["new", "mid", "old"]
    assert [i.key for i in s.query(MemoryQuery(limit=2))] == ["new", "mid"]
    assert s.query(MemoryQuery(limit=0)) == []


def test_same_tick_items_keep_insertion_order():
    """Windows clock resolution is ~15ms: identical timestamps must not scramble
    ordering. The zero-padded key sequence is the tie-break."""
    same = 1000.0
    s = _store(
        _item("session:s:000001", timestamp=same),
        _item("session:s:000002", timestamp=same),
        _item("session:s:000003", timestamp=same),
    )
    assert [i.key[-6:] for i in s.query(MemoryQuery())] == ["000003", "000002", "000001"]
    assert [i.key[-6:] for i in s.query(MemoryQuery(limit=2))] == ["000003", "000002"]


def test_query_combines_criteria_with_and():
    s = _store(
        _item("match", "about rust", timestamp=150.0, importance=0.9, tags=("session",)),
        _item("wrong_tag", "about rust", timestamp=150.0, importance=0.9),
        _item("wrong_time", "about rust", timestamp=999.0, importance=0.9, tags=("session",)),
    )
    q = MemoryQuery(tags=["session"], time_range=(100.0, 200.0), min_importance=0.5,
                    semantic_query="rust")
    assert [i.key for i in s.query(q)] == ["match"]


def test_empty_query_returns_everything_live():
    s = _store(_item("a"), _item("b"))
    assert len(s.query(MemoryQuery())) == 2


# --- observability ---------------------------------------------------------
def test_store_counts_puts():
    s = _store(_item("a"), _item("b"))
    assert s.stats["put"] == 2


def test_store_is_engine_swappable_via_port():
    """DoD: the store is used through IMemoryStore, nothing else."""
    from contracts.i_memory import IMemoryStore
    assert isinstance(InMemoryMemoryStore(), IMemoryStore)
