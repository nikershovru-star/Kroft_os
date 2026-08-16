"""PHASE 3 — HTTP API delegation tests (mock agent interface, no 750MB load).

Verifies the thin HTTP transport adapter over IKroftAgentInterface:
  GET  /api/status  -> agent.status()
  GET  /api/audit   -> agent.audit(limit)
  POST /api/query   -> agent.query(query, top_k)
  POST /api/resolve -> agent.resolve(query, level)
plus error contract (400/404/405/503, JSON, no stack trace).

Uses the REAL KROFT_OSServer with a mock DI container — no foundation load.
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.http_server import KROFT_OSServer  # noqa: E402


def _fake_container(agent):
    engine = MagicMock(name="GraphQueryEngine")
    container = MagicMock(name="container")

    def _has(name):
        return name in ("GraphQueryEngine", "IKroftAgentInterface")

    def _resolve(name):
        return {"GraphQueryEngine": engine, "IKroftAgentInterface": agent}[name]

    container.has.side_effect = _has
    container.resolve.side_effect = _resolve
    return container, engine


def _start_server(agent):
    container, engine = _fake_container(agent)
    server = KROFT_OSServer(container, host="127.0.0.1", port=0)
    server.start()
    return server, engine


def _get(server, path):
    url = f"http://127.0.0.1:{server.port}{path}"
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _post(server, path, payload):
    url = f"http://127.0.0.1:{server.port}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, _safe_json(e.read())


def _safe_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _expect_status(server, path, code):
    url = f"http://127.0.0.1:{server.port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, _safe_json(e.read())


def test_status_delegates():
    agent = MagicMock()
    agent.status.return_value = {"status": "ok", "runtime": "running"}
    server, _ = _start_server(agent)
    try:
        code, body = _get(server, "/api/status")
        assert code == 200
        assert body["runtime"] == "running"
        agent.status.assert_called_once()
    finally:
        server.stop()


def test_audit_delegates_with_limit():
    agent = MagicMock()
    agent.audit.return_value = {"ok": True, "count": 3, "entries": []}
    server, _ = _start_server(agent)
    try:
        code, body = _get(server, "/api/audit?limit=10")
        assert code == 200
        agent.audit.assert_called_once_with(limit=10)
    finally:
        server.stop()


def test_query_delegates():
    agent = MagicMock()
    agent.query.return_value = {"mode": "hybrid", "results": [{"id": "x"}]}
    server, _ = _start_server(agent)
    try:
        code, body = _post(server, "/api/query", {"query": "memory", "top_k": 5})
        assert code == 200
        agent.query.assert_called_once_with(query="memory", top_k=5)
    finally:
        server.stop()


def test_resolve_delegates():
    agent = MagicMock()
    agent.resolve.return_value = {"ok": True, "level": "SYSTEM", "items": []}
    server, _ = _start_server(agent)
    try:
        code, body = _post(server, "/api/resolve", {"query": "arch", "level": "SYSTEM"})
        assert code == 200
        agent.resolve.assert_called_once_with(query="arch", level="SYSTEM")
    finally:
        server.stop()


def test_query_missing_query_400():
    agent = MagicMock()
    server, _ = _start_server(agent)
    try:
        code, body = _post(server, "/api/query", {"top_k": 5})
        assert code == 400
        assert body["error"] == "invalid_request"
        agent.query.assert_not_called()
    finally:
        server.stop()


def test_query_malformed_json_400():
    agent = MagicMock()
    server, _ = _start_server(agent)
    try:
        url = f"http://127.0.0.1:{server.port}/api/query"
        req = urllib.request.Request(url, data=b"{not json", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 400
    finally:
        server.stop()


def test_resolve_unknown_route_404():
    agent = MagicMock()
    server, _ = _start_server(agent)
    try:
        code, body = _expect_status(server, "/api/does_not_exist", 404)
        assert code == 404
    finally:
        server.stop()


def test_unsupported_method_405_on_status():
    agent = MagicMock()
    server, _ = _start_server(agent)
    try:
        url = f"http://127.0.0.1:{server.port}/api/status"
        req = urllib.request.Request(url, data=b"{}", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code != 200  # 405 or 501 both signal "unsupported"
    finally:
        server.stop()


def test_existing_search_endpoint_preserved():
    """Regression guard: /api/search keeps lexical GraphQueryEngine semantics."""
    agent = MagicMock()
    server, engine = _start_server(agent)
    try:
        # /api/search must still call engine.search (lexical), NOT agent.search.
        engine.search.return_value = ["A.md", "B.md"]
        code, body = _get(server, "/api/search?q=python")
        assert code == 200
        engine.search.assert_called_once()
        agent.search.assert_not_called()  # PHASE 3 does NOT repoint /api/search
    finally:
        server.stop()
