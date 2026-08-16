"""Ensemble orchestrator port — parallel multi-model call + merge (ТЗ-ECHO, E1/E4/E5).

K1-compliant: stdlib + contracts only. Takes a ``ModelQuery`` and a list of underlying
``ILlm`` clients, calls them in parallel, and merges their ``LlmResponse``s into one
``EnsembleResult`` (which carries both the merged ``LlmResponse`` and the per-model raw
responses for observability). The merge is strategy-driven (E4: best-confidence; E5:
RRF-over-text, added later).

This is the "Echo" part of the pattern: one request -> N free/open models -> combined
answer. It reuses the existing ``ILlm`` port for each candidate (KROFT one-port-per-
boundary — no second LLM port). Network I/O stays inside each ``ILlm`` (IHttpTransport).

K5: reuses ILlm / LlmResponse / ModelQuery. No provider SDK, no new transport.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from contracts.i_llm import ILlm, LlmResponse, ModelQuery


class MergeStrategy(str, Enum):
    """How to combine N model responses into one.

    BEST_CONFIDENCE: pick the response with the highest confidence/proxy (E4 default).
    RRF_TEXT: RRF-like merge over sentence/fact units (E5, added later).
    """

    BEST_CONFIDENCE = "best_confidence"
    RRF_TEXT = "rrf_text"


@dataclass
class EnsembleResult:
    """Merged result of an ensemble call.

    ``response`` is the single ``LlmResponse`` handed to the kernel advisor (so the
    ensemble is drop-in compatible with the ILlm contract). ``per_model`` keeps every
    raw response keyed by provider name for logging/eval. ``latency_ms`` is the WALL
    time of the parallel call (max, not sum) — this is what the E-final latency budget
    (<= +20% vs single model) is measured against.
    """

    response: LlmResponse
    per_model: Dict[str, LlmResponse] = field(default_factory=dict)
    strategy: MergeStrategy = MergeStrategy.BEST_CONFIDENCE
    latency_ms: float = 0.0
    cost: float = 0.0


class IEnsembleOrchestrator(ABC):
    """Port: run N models in parallel and merge their answers."""

    @abstractmethod
    def run(
        self,
        query: ModelQuery,
        clients: List[ILlm],
        strategy: MergeStrategy = MergeStrategy.BEST_CONFIDENCE,
    ) -> EnsembleResult:
        """Call each client (in parallel) for ``query`` and merge into one result.

        Contract:
          - MUST call all non-None clients (clients may be empty -> caller handles).
          - On a single client, delegates and returns its response (no merge overhead).
          - MUST NOT crash if one model fails: failed responses are excluded from the
            merge; if ALL fail, return an ``EnsembleResult`` whose ``response.error`` is
            set (do not raise — the router/kernel decides retrieval-only, LLM-01).
          - ``latency_ms`` = wall-clock of the parallel fan-out (max, not sum).
        """
        raise NotImplementedError
