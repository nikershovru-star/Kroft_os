"""Model Registry (Wave 4, candidate ADR-033).

Aggregates declared catalogs from multiple providers (OmniRoute, Ollama, ...)
into one capability-indexed directory. This is what makes the two-pole Model
Platform (free-online + local-offline) useful: the Router (Wave 5/6) queries
the registry instead of knowing about each backend.

Depends only on contracts — providers register their IModelMetadata.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from contracts.i_llm import IModelMetadata, ModelInfo, ModelQuery


class ModelRegistry(IModelMetadata):
    """Unified model directory across providers."""

    def __init__(self) -> None:
        self._sources: List[IModelMetadata] = []
        self._by_id: Dict[str, ModelInfo] = {}

    def register_source(self, source: IModelMetadata) -> None:
        self._sources.append(source)
        for m in source.catalog():
            self._by_id[m.id] = m

    def register_model(self, model: ModelInfo) -> None:
        """Directly declare a model (hand-built catalog, no adapter needed)."""
        self._by_id[model.id] = model

    def catalog(self) -> List[ModelInfo]:
        # single source of truth is _by_id (filled by register_source + register_model)
        return list(self._by_id.values())

    def capabilities(self, model_id: str) -> Optional[ModelInfo]:
        return self._by_id.get(model_id)

    # --- selection helper (used by Router, Wave 5/6) -----------------------
    def select(self, query: ModelQuery) -> Optional[ModelInfo]:
        """Pick the best declared model for a query across all sources."""
        candidates = [
            m for m in self.catalog()
            if (not query.reasoning or m.reasoning)
            and (not query.local or m.local)
            and (not query.json_mode or m.json_mode)
            and (not query.cheap or m.free)
            and (query.context_window == 0 or m.context_window >= query.context_window)
        ]
        if not candidates:
            return None
        if query.preferred_provider:
            for m in candidates:
                if m.id == query.preferred_provider or m.provider == query.preferred_provider:
                    return m
        # Tiebreak: honour the locality the query asked for. When local=False we
        # must prefer online models (otherwise a local model always wins because
        # it sorts first), and vice-versa. Largest context window breaks ties.
        want_local = query.local
        candidates.sort(key=lambda m: (m.local != want_local, -m.context_window))
        return candidates[0]
