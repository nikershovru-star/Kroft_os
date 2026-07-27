"""Embedding adapters (Stage 29).

MockEmbeddingAdapter  — deterministic 128-dim unit vector from SHA-256.
                        Zero external deps; used in tests and as the default
                        wiring so `semantic` works out of the box.
OpenAIEmbeddingAdapter — optional, stdlib urllib only. Needs OPENAI_API_KEY.

Arch: adapters may import contracts + stdlib.
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import List, Optional

from contracts import IEmbedding


class MockEmbeddingAdapter(IEmbedding):
    """Deterministic embedding for testing. 128-dim, L2-normalized.

    NOT real semantics — same text always maps to the same vector, similar
    texts do NOT map to nearby vectors. It exists to exercise the vector
    infrastructure (index, cosine, top-k, snapshot) hermetically.
    """

    def embed(self, text: str) -> List[float]:
        h = hashlib.sha256((text or "").encode("utf-8")).digest()  # 32 bytes
        vec: List[float] = []
        for j in range(4):
            for i in range(32):
                val = ((h[i] / 255.0 + j * 0.25) % 1.0) * 2 - 1
                vec.append(val)
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


class OpenAIEmbeddingAdapter(IEmbedding):
    """Optional OpenAI embeddings via stdlib urllib. Lazy-fail if no key."""

    def __init__(self, model: str = "text-embedding-3-small",
                 api_key: Optional[str] = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def embed(self, text: str) -> List[float]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        import json
        import urllib.request
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps({"input": text, "model": self.model}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["data"][0]["embedding"]
