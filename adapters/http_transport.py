"""Real HTTP transport (ТЗ-LLM-LIVE-01, ADR-079) — stdlib urllib only, K6-clean.

Implements the ``IHttpTransport`` port (contracts/i_http.py) with the standard library
``urllib.request`` module — ZERO third-party SDKs (no ``requests``/``httpx``/``openai`` in
the domain layer, per K6). The network boundary is funneled through this port so LLM
adapters (OpenAiCompatibleClient, adapters/openai_compatible.py) never touch a provider
SDK directly and remain testable with a fake transport.

K1/K6: depends ONLY on contracts/i_http (the port + typed transport errors) + stdlib.
Adapters may import contracts + stdlib (gate rule: ``adapters.* -> contracts + stdlib``),
so this module is lawfully placed in ``adapters/``.

Error mapping (the contract requires typed transport errors, NOT generic Exception):
- socket.timeout / urllib timeout -> TransportTimeout
- urllib.error.URLError (connection refused / DNS) -> TransportError
- http.client.HTTPException / other I/O -> TransportError
- non-2xx HTTP status -> TransportError (the adapter maps non-2xx to LLMError downstream)
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Dict, Optional

from contracts.i_http import HttpResponse, IHttpTransport, TransportError, TransportTimeout


class HttpTransport(IHttpTransport):
    """Real HTTP client over stdlib ``urllib`` — backend-agnostic, no provider SDK.

    Point ``base_url`` at any OpenAI-compatible endpoint (Ollama localhost:11434/v1,
    LM Studio, vLLM, a gateway). The client that consumes this transport owns the
    URL/path composition; this transport only performs the raw request and normalizes
    the response/errors.
    """

    def __init__(self, base_url: str = "", *, default_timeout: float = 30.0,
                 headers: Optional[Dict[str, str]] = None) -> None:
        # base_url is optional: callers may pass full URLs to ``request``. When set,
        # it is used as a prefix for relative paths (convenience for chat completions).
        self._base = base_url.rstrip("/") if base_url else ""
        self._default_timeout = default_timeout
        self._default_headers = dict(headers or {})

    def request(self, method: str, url: str,
                headers: Optional[Dict[str, str]] = None,
                body: Optional[str] = None,
                timeout: float = 30.0) -> HttpResponse:
        target = url if url.startswith("http://") or url.startswith("https://") else f"{self._base}{url}"
        req_headers = dict(self._default_headers)
        if headers:
            req_headers.update(headers)

        data = body.encode("utf-8") if body is not None else None
        req = urllib.request.Request(target, data=data, method=method.upper())
        for k, v in req_headers.items():
            req.add_header(k, v)

        effective_timeout = timeout if timeout and timeout > 0 else self._default_timeout
        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                resp_headers = {k.lower(): v for k, v in resp.getheaders()}
                return HttpResponse(status=resp.status, body=raw, headers=resp_headers)
        except urllib.error.HTTPError as e:
            # Server responded with an error status (4xx/5xx): read the body if any.
            raw = ""
            try:
                raw = e.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 — body read is best-effort
                pass
            raise TransportError(f"HTTP {e.code} from {target}: {raw[:200]}") from e
        except socket.timeout as e:
            raise TransportTimeout(f"socket timeout after {effective_timeout}s on {target}") from e
        except urllib.error.URLError as e:
            # Connection refused / DNS / no route — network-level failure.
            raise TransportError(f"URLError {e.reason} on {target}") from e
        except (ConnectionError, OSError) as e:
            # Local socket errors (e.g. [WinError 10061] refused) — network-level.
            raise TransportError(f"connection error {e} on {target}") from e
        except ValueError as e:
            # e.g. unknown URL type / malformed URL.
            raise TransportError(f"bad request {e} on {target}") from e
