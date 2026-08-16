"""C.6 — Brave Search adapter for the external-knowledge port (ТЗ-ECHO Stage 4).

K1: imports only ``contracts`` + stdlib at module load. The HTTP call uses the
existing ``IHttpTransport`` (contracts/i_http.py) so it reuses the SAME
transport layer as every other adapter — NO new networking code. The third-party
key is read from an env var (BRAVE_API_KEY) and passed through the transport; if
absent the adapter degrades to ``[]`` (never raises) — external lookup is
best-effort and OFFLINE-SAFE, matching IExternalSearch contract.

Reuses ``IExternalSearch`` / ``ExternalResult`` from contracts/i_external_search.py
(K5: do NOT create a second search port). Brave is a provider option alongside
the already-shipped DuckDuckGo adapter (adapters/web_search_adapter.py); this
file adds the Brave-specific transport binding only.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List
from urllib.parse import urlencode, urlparse

from contracts.i_external_search import ExternalResult, IExternalSearch
from contracts.i_http import IHttpTransport

logger = logging.getLogger(__name__)

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchAdapter(IExternalSearch):
    """Opt-in external web search via Brave Search API.

    Usage:
        adapter = BraveSearchAdapter(transport, api_key=os.getenv("BRAVE_API_KEY"))
        results = adapter.search("cognitive kernel architecture", top_k=5)
    """

    def __init__(
        self,
        transport: IHttpTransport,
        api_key: str = "",
        top_k: int = 5,
    ) -> None:
        self._transport = transport
        self._api_key = api_key
        self._top_k = top_k

    def search(self, query: str, top_k: int = 5) -> List[ExternalResult]:
        if not self._api_key:
            logger.warning("[Brave] no API key -> degraded to [] (offline-safe)")
            return []
        url = f"{_BRAVE_ENDPOINT}?{urlencode({'q': query, 'count': max(1, top_k)})}"
        try:
            resp = self._transport.request(
                "GET", url,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
                timeout=8.0,
            )
        except Exception as exc:  # noqa: BLE001 — network / rate-limit / offline
            logger.warning("[Brave] external search failed (degraded to []): %s", exc)
            return []
        if resp.status < 200 or resp.status >= 300 or not resp.body:
            return []
        try:
            payload = json.loads(resp.body)
        except Exception:  # noqa: BLE001 — malformed JSON
            return []
        out: List[ExternalResult] = []
        for item in (payload.get("web", {}).get("results", []) or [])[:top_k]:
            url = item.get("url") or ""
            if not url:
                continue
            host = urlparse(url).netloc or "brave"
            out.append(
                ExternalResult(
                    title=item.get("title", "") or url,
                    url=url,
                    snippet=item.get("description", "") or "",
                    source=host,
                    score=float(item.get("score", 0.0) or 0.0),
                )
            )
        return out
