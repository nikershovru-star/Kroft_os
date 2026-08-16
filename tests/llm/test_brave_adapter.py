"""Stage 4 — BraveSearchAdapter (deterministic, fake transport, no network).

Proves: IExternalSearch contract compliance, graceful [] on missing key,
correct parsing of Brave JSON payload, and reuse of IHttpTransport (K5).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from contracts.i_external_search import IExternalSearch
from contracts.i_http import HttpResponse
from adapters.brave_search_adapter import BraveSearchAdapter


class _FakeTransport:
    def __init__(self, status=200, body="{}"):
        self._status = status
        self._body = body
        self.last = None

    def request(self, method, url, headers=None, body=None, timeout=30.0):
        self.last = (method, url, headers, timeout)
        return HttpResponse(status=self._status, body=self._body)


def test_implements_iexternalsearch():
    t = _FakeTransport()
    a = BraveSearchAdapter(t, api_key="k")
    assert isinstance(a, IExternalSearch)


def test_no_key_degrades_to_empty():
    t = _FakeTransport()
    a = BraveSearchAdapter(t, api_key="")
    assert a.search("query") == []
    assert t.last is None  # no network call without key


def test_parses_brave_payload():
    payload = (
        '{"web":{"results":['
        '{"title":"CK","url":"https://example.com/ck","description":"cognitive kernel","score":0.9},'
        '{"title":"OS","url":"https://other.org/os","description":"operating system"}'
        "]}}"
    )
    t = _FakeTransport(status=200, body=payload)
    a = BraveSearchAdapter(t, api_key="k", top_k=5)
    res = a.search("cognitive kernel", top_k=5)
    assert len(res) == 2
    assert res[0].url == "https://example.com/ck"
    assert res[0].snippet == "cognitive kernel"
    assert res[0].source == "example.com"
    assert res[0].score == pytest.approx(0.9)
    # request used GET + auth header + timeout
    assert t.last[0] == "GET"
    assert t.last[2].get("X-Subscription-Token") == "k"
    assert t.last[3] == 8.0


def test_non_200_degrades_to_empty():
    t = _FakeTransport(status=500, body="err")
    a = BraveSearchAdapter(t, api_key="k")
    assert a.search("q") == []


def test_malformed_json_degrades_to_empty():
    t = _FakeTransport(status=200, body="not json")
    a = BraveSearchAdapter(t, api_key="k")
    assert a.search("q") == []


def test_transport_exception_degrades_to_empty():
    class _Boom:
        def request(self, *a, **k):
            raise RuntimeError("network down")

    a = BraveSearchAdapter(_Boom(), api_key="k")
    assert a.search("q") == []
