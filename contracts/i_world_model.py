"""World Model port (ТЗ-WM-01 / ADR-047) — K1-compliant: contracts + stdlib only.

The World Model is an ADVISOR over WorldState (ADR-047): it projects the future
consequences of an action / plan so planning + decision can rank candidates by
PREDICTED utility instead of word overlap. The final pick stays with the
deterministic Decision Engine (I-09) — the model only advises.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from contracts.cognitive_domain import (
    Action,
    ConfidenceScore,
    Intent,
    Plan,
    PredictedState,
    WorldState,
)
from contracts.i_cognitive_kernel import IValueSystem


class IWorldModel(ABC):
    """Predictive model over WorldState (ТЗ-WM-01).

    Three operations (ADR-047):
      - predict(world, action, horizon) -> PredictedState for ONE action.
      - simulate(world, plan) -> List[PredictedState], one per plan step (rollout).
      - evaluate(predicted, intent, values) -> float predicted utility in [0,1].

    Confidence of a PredictedState MUST fall with `horizon` (further = less certain).
    Worlds with no relevant facts yield LOW-confidence predictions.
    """

    @abstractmethod
    def predict(self, world: WorldState, action: Action, horizon: int = 1) -> PredictedState:
        """Project `world` after `action`, `horizon` steps ahead."""

    @abstractmethod
    def simulate(self, world: WorldState, plan: Plan, horizon: int = 1) -> List[PredictedState]:
        """Roll out `plan` step-by-step; return one PredictedState per plan step."""

    @abstractmethod
    def evaluate(self, predicted: PredictedState, intent: Intent,
                 values: Optional[IValueSystem] = None) -> float:
        """Predicted utility of a state w.r.t. the Intent (0..1)."""
