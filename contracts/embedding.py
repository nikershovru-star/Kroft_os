"""IEmbedding — vector embedding port (Stage 29).

Adapters (MockEmbeddingAdapter, OpenAIEmbeddingAdapter) implement this port;
services (SemanticIndex consumers) depend only on the abstraction.
"""
from __future__ import annotations

import abc
from typing import List


class IEmbedding(abc.ABC):
    """Port: turn text into a dense float vector."""

    @abc.abstractmethod
    def embed(self, text: str) -> List[float]:
        """Return a dense float vector representing *text*."""
        raise NotImplementedError
