"""Data transfer objects for the Echo-pattern router/ensemble (ТЗ-ECHO, E1).

These wrap the existing ``contracts.i_llm`` DTOs (ModelQuery / LlmResponse) with
routing/ensemble metadata (category, chosen providers, wall timings, per-model cost)
without modifying the kernel-facing contract. The kernel advisor still consumes a plain
``LlmResponse``; RouterResult/EnsembleResult are the richer envelopes used by the router
layer and by logging/observability (E6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from contracts.i_llm import LlmResponse, ModelQuery


@dataclass
class RouterRequest:
    """A request handed to the router.

    ``query`` is the underlying LLM query (reused as-is). ``category`` may be pre-filled
    by an upstream classifier (E3); if None, the policy classifies from the prompt.
    """

    query: ModelQuery
    category: Optional[str] = None


@dataclass
class RouterResult:
    """Outcome of routing a single request.

    ``response`` is the final ``LlmResponse`` (from the chosen single model, or the merged
    ensemble answer). ``category`` records where we routed; ``chosen_providers`` lists the
    provider names that actually participated (1 for single, N for ensemble).
    """

    response: LlmResponse
    category: str
    chosen_providers: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    cost: float = 0.0
    used_ensemble: bool = False


# Re-export LlmResponse / ModelQuery for callers that import via this package.
__all__ = ["RouterRequest", "RouterResult", "LlmResponse", "ModelQuery"]
