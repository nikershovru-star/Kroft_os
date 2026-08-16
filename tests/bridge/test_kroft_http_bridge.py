"""PHASE 4 — KroftHttpBridge (Hermes HTTP client) tests.

Fast unit tests mock urllib so no KROFT Runtime / 750MB foundation is loaded.
Verifies the external-agent boundary talks ONLY to the universal HTTP contract
(/api/status | /api/search | /api/query | /api/resolve | /api/audit) and never
imports/instantiates KROFT internals (transport-only delegation).
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridges.kroft_bridge import KroftHttpBridge, KroftToolResult  # noqa: E402


def _mock_urlopen(status, body):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(body).encode("utf-8")
    return resp


def test_status_ok():
    body = {"status": "ok", "runtime": "running", "node_id": "n1"}
    with patch.object(KroftHttpBridge, "_get", return_value=(200, body)):
        b = KroftHttpBridge("http://127.0.0.1:8080", node_id="n1")
        r = b.status()
    assert r.ok
    assert r.result["runtime"] == "running"


def test_status_transport_error():
    with patch.object(KroftHttpBridge, "_get", return_value=(503, {"error": "transport"})):
        b = KroftHttpBridge("http://127.0.0.1:8080")
        r = b.status()
    assert not r.ok
    assert r.errors


def test_search_reuses_existing_endpoint():
    # /api/search returns a list of node ids (lexical) — bridge reuses it.
    with patch.object(KroftHttpBridge, "_get", return_value=(200, ["A.md", "B.md"])):
        b = KroftHttpBridge("http://127.0.0.1:8080")
        r = b.search("memory", top_k=5)
    assert r.ok
    assert r.metadata["mode"] == "lexical"
    assert [i["id"] for i in r.result["items"]] == ["A.md", "B.md"]


def test_query_delegates_to_agent_interface():
    body = {"mode": "hybrid", "results": [{"id": "x"}]}
    with patch.object(KroftHttpBridge, "_post", return_value=(200, body)):
        b = KroftHttpBridge("http://127.0.0.1:8080")
        r = b.query("arch", top_k=3)
    assert r.ok
    assert r.metadata["mode"] == "hybrid"


def test_resolve_delegates():
    body = {"ok": True, "level": "SYSTEM", "items": []}
    with patch.object(KroftHttpBridge, "_post", return_value=(200, body)):
        b = KroftHttpBridge("http://127.0.0.1:8080")
        r = b.resolve("fed", resolution="system")
    assert r.ok
    assert r.metadata["level"] == "SYSTEM"


def test_audit_delegates():
    body = {"ok": True, "count": 2, "entries": []}
    with patch.object(KroftHttpBridge, "_get", return_value=(200, body)):
        b = KroftHttpBridge("http://127.0.0.1:8080")
        r = b.audit(limit=10)
    assert r.ok


def test_factory():
    b = __import__("bridges.kroft_bridge", fromlist=["kroft_http_bridge"]).kroft_http_bridge(
        "http://127.0.0.1:9", node_id="x"
    )
    assert isinstance(b, KroftHttpBridge)
    assert b._node_id == "x"
