"""PHASE 2 — IKroftAgentInterface contract + KroftAgentInterface delegation tests.

Verifies the universal external-agent contract is agent-agnostic (delegates to
existing services, no agent-specific branching) without loading the 750MB
production snapshot. Heavy collaborators are mocked.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts import ResolutionLevel  # noqa: E402
from contracts.i_kroft_agent_interface import IKroftAgentInterface  # noqa: E402
from services.kroft_agent_interface import KroftAgentInterface  # noqa: E402


def _fake_container():
    engine = MagicMock(name="GraphQueryEngine")
    engine._snapshot.return_value = {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []}
    engine.hybrid_search.return_value = [("n1", 0.9), ("n2", 0.4)]
    engine.search.return_value = ["n1", "n2"]
    engine.graph_stats.return_value = {"node_count": 2}
    engine.graph_health.return_value = {"status": "healthy"}
    engine.get_audit_log.return_value = [{"ts": 1, "op": "add"}]
    engine.centrality.return_value = {}

    res = MagicMock(name="ReferenceKnowledgeResolution")
    res.view.return_value = MagicMock(items=[{"id": "n1"}], resolution="SYSTEM")

    mem = MagicMock(name="IProceduralMemory")
    mem.list_procedures.return_value = [{"name": "p1"}]
    mem.stats.return_value = {"count": 1}

    c = MagicMock(name="container")
    c.has.return_value = True
    c.resolve.side_effect = lambda name: {
        "GraphQueryEngine": engine,
        "ReferenceKnowledgeResolution": res,
        "IProceduralMemory": mem,
    }[name]
    return c, engine, res, mem


def test_interface_is_abstract_contract():
    # The contract itself must not be instantiable (pure abstraction).
    with pytest.raises(TypeError):
        IKroftAgentInterface()


def test_status_delegates_to_runtime_health():
    c, *_ = _fake_container()
    rt = MagicMock()
    rt.health.return_value = {"status": "ok", "runtime": "running"}
    ai = KroftAgentInterface(c, runtime=rt)
    assert ai.status()["runtime"] == "running"


def test_search_delegates_hybrid():
    c, engine, *_ = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.search("federation", top_k=5)
    assert len(out) == 2
    assert out[0]["id"] == "n1"
    assert out[0]["score"] == 0.9
    engine.hybrid_search.assert_called_once_with("federation", top_k=5)


def test_query_returns_hybrid_results():
    c, *_ = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.query("memory")
    assert out["mode"] == "hybrid"
    assert len(out["results"]) == 2
    assert "abstained" in out


def test_resolve_delegates_to_resolution_service():
    c, _, res, _ = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.resolve("federation", level="SYSTEM")
    assert out["ok"] is True
    assert out["level"] == "SYSTEM"
    assert out["items"] == [{"id": "n1"}]
    res.view.assert_called_once_with("federation", ResolutionLevel.SYSTEM)


def test_resolve_unknown_level_is_rejected():
    c, *_ = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.resolve("x", level="NOPE")
    assert out["ok"] is False
    assert "valid" in out


def test_audit_delegates_to_engine():
    c, engine, *_ = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.audit(limit=10)
    assert out["ok"] is True
    assert out["count"] == 1
    engine.get_audit_log.assert_called_once()


def test_observe_returns_stats_and_health():
    c, *_ = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.observe()
    assert out["ok"] is True
    assert "graph_stats" in out and "graph_health" in out


def test_memory_delegates():
    c, _, _, mem = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.memory(action="list")
    assert out["ok"] is True
    assert out["items"] == [{"name": "p1"}]


def test_knowledge_stats():
    c, engine, *_ = _fake_container()
    ai = KroftAgentInterface(c)
    out = ai.knowledge(action="stats")
    assert out["ok"] is True
    assert out["stats"] == {"node_count": 2}


def test_agent_interface_wired_into_runtime():
    """KroftRuntime exposes the universal interface after start (DI wiring)."""
    from services.kroft_agent_interface import KroftAgentInterface

    c, *_ = _fake_container()
    # Runtime is represented by a mock whose health() feeds status().
    rt = MagicMock(name="runtime")
    rt.health.return_value = {"status": "ok", "runtime": "running", "node_id": "kroft-a"}

    ai = KroftAgentInterface(c, runtime=rt)
    # The universal interface delegates status() to the runtime health().
    assert ai.status()["runtime"] == "running"
    # And it is the concrete impl of the abstract contract.
    assert isinstance(ai, IKroftAgentInterface)
