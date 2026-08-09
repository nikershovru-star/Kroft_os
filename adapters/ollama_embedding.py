"""Local OpenAI-compatible embedding adapter (Slice: local embedding retrieval).

Implements the existing ``IEmbedding`` port (contracts) against any OpenAI-compatible
``/v1/embeddings`` endpoint — Ollama (default ``http://localhost:11434/v1``) or LM Studio.
Stdlib urllib only (K5, no new deps). Graceful on unavailability: ``embed`` raises, and
callers (CognitiveKernel._retrieve_similar_episodes) fall back to keyword-overlap.

Base URL from env ``KROFT_EMBEDDING_URL`` (default ``http://localhost:11434/v1``).
No API key required for local Ollama; ``api_key`` is optional and only sent if set.

Arch: adapters may import contracts + stdlib. No kernel/contracts change (K6).
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Optional

from contracts import IEmbedding

DEFAULT_BASE_URL = "http://localhost:11434/v1"
# ТЗ: default embedding model = bge-m3 (best R@5 on the KROFT_KNOWLEDGE golden set).
# Graceful fallback chain: bge-m3 -> nomic-embed-text -> (raise -> caller keyword-overlap).
DEFAULT_MODEL = "bge-m3"
FALLBACK_MODELS = ("nomic-embed-text",)


class OllamaEmbeddingAdapter(IEmbedding):
    """Local embeddings via OpenAI-compatible /v1/embeddings (Ollama/LM Studio).

    Lazy-fail semantics: the constructor does NOT probe the server (so a missing
    local model is non-fatal at wiring time). ``embed`` performs the HTTP call and
    lets transport errors propagate — the kernel's retrieval path catches them and
    degrades to keyword-overlap. This keeps the default boot deterministic and
    network-free when no local embedding server is running.

    Model fallback (ТЗ): if the configured model (default bge-m3) is unavailable on
    the local server, ``embed`` retries each FALLBACK_MODELS entry once before
    re-raising; callers (CognitiveKernel._retrieve_similar_episodes) then degrade to
    keyword-overlap. Non-fatal at boot: a missing model never crashes wiring.
    """

    def __init__(self, model: str = DEFAULT_MODEL,
                 base_url: Optional[str] = None,
                 api_key: Optional[str] = None) -> None:
        self.model = model
        # base_url is the *API base* (.../v1); the embeddings path is appended.
        self.base_url = (base_url or os.environ.get("KROFT_EMBEDDING_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("KROFT_EMBEDDING_API_KEY") or None

    def _embed_with(self, model: str, text: str) -> List[float]:
        url = f"{self.base_url}/embeddings"
        payload = json.dumps({"input": text, "model": model}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["data"][0]["embedding"]

    def embed(self, text: str) -> List[float]:
        # Try the configured model first, then each fallback once.
        tried = [self.model, *FALLBACK_MODELS]
        last_err: Optional[Exception] = None
        for m in tried:
            try:
                return self._embed_with(m, text)
            except Exception as e:  # model missing / server down / timeout
                last_err = e
                continue
        # All models failed -> let the caller degrade to keyword-overlap.
        raise last_err if last_err is not None else RuntimeError("embedding unavailable")
