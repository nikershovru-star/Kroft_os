"""Stage 28 - Basic Auth tests (5).

SimpleAuthService (services/, secrets-only) + HTTP guard in the adapter:
with "AuthService" registered in DI every route except /api/login and
/login.html requires the kroft_os_session cookie. Cookie extraction is
manual — http.client does NOT parse Set-Cookie (known collision).
"""
from __future__ import annotations

import http.client
import json
import socket
import time

import pytest

from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
)
from runtime import CapabilityRegistry
from services import GraphQueryEngine, SimpleAuthService
from adapters.http_server import KROFT_OSServer


def _wait_ready(host, port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"server on {host}:{port} never came up")


@pytest.fixture()
def auth_server():
    c = DependencyContainer()
    g = InMemoryGraphBuilder()
    g.add_node("A", "A", {})
    c.register_instance("IGraphBuilder", g)
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    c.register_instance("AuthService", SimpleAuthService("admin", "secret"))
    c.register_factory("GraphQueryEngine", lambda: GraphQueryEngine(g))
    server = KROFT_OSServer(c, host="127.0.0.1", port=0)
    server.start()
    _wait_ready("127.0.0.1", server.port)
    yield server
    server.stop()


def _request(port, method, path, body=None, cookie=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/json"
        conn.request(method, path, json.dumps(body), headers)
    else:
        conn.request(method, path, headers=headers)
    return conn.getresponse()


def _login(port, user="admin", passwd="secret"):
    r = _request(port, "POST", "/api/login", body={"user": user, "pass": passwd})
    set_cookie = r.getheader("Set-Cookie") or ""
    # "kroft_os_session=<hex>; HttpOnly; Path=/" -> first pair only.
    cookie = set_cookie.split(";", 1)[0] if set_cookie else None
    return r, cookie


def test_login_success(auth_server):
    r, cookie = _login(auth_server.port)
    assert r.status == 200
    assert json.loads(r.read().decode("utf-8")) == {"ok": True}
    assert cookie is not None and cookie.startswith("kroft_os_session=")
    token = cookie.split("=", 1)[1]
    assert len(token) == 64  # secrets.token_hex(32)


def test_login_failure(auth_server):
    r, cookie = _login(auth_server.port, passwd="WRONG")
    assert r.status == 401
    assert cookie is None or "kroft_os_session=" not in (cookie or "")


def test_protected_without_cookie(auth_server):
    r = _request(auth_server.port, "GET", "/api/graph")
    assert r.status == 401
    # "/" gets a browser-friendly redirect to the login form instead.
    r2 = _request(auth_server.port, "GET", "/")
    assert r2.status == 302
    assert r2.getheader("Location") == "/login.html"
    # login page itself must stay reachable (no lockout loop).
    r3 = _request(auth_server.port, "GET", "/login.html")
    assert r3.status == 200


def test_protected_with_cookie(auth_server):
    _, cookie = _login(auth_server.port)
    r = _request(auth_server.port, "GET", "/api/graph", cookie=cookie)
    assert r.status == 200
    data = json.loads(r.read().decode("utf-8"))
    assert [n["id"] for n in data["nodes"]] == ["A"]


def test_logout_revokes(auth_server):
    _, cookie = _login(auth_server.port)
    r = _request(auth_server.port, "GET", "/api/logout", cookie=cookie)
    assert r.status == 200
    # Same token afterwards -> 401 (session revoked server-side, not just
    # cookie cleared client-side).
    r2 = _request(auth_server.port, "GET", "/api/graph", cookie=cookie)
    assert r2.status == 401
