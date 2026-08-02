"""Reference World Model (ТЗ-WM-01) — deterministic, LLM-free (I-09).

K1-compliant: imports ONLY contracts + stdlib. No service/adapter/runtime imports.

The World Model is an ADVISOR (ADR-047): it projects the consequences of an action /
plan so planning + decision rank candidates by PREDICTED utility, not word overlap.
The final pick stays with the deterministic Decision Engine.

Key property (acceptance): predicted **confidence falls monotonically with horizon**
(further projection = more uncertain). Worlds with no relevant facts yield LOW
confidence. Every PredictedState carries a CausalMark from the node's shared clock
(ТЗ-RE-01 flag 1), so node_origin == node_id.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from contracts.cognitive_domain import (
    Action,
    CausalMark,
    ConfidenceScore,
    Intent,
    NodeLamportClock,
    Plan,
    PredictedState,
    ProvenanceType,
    WorldState,
)
from contracts.i_cognitive_kernel import IValueSystem
from contracts.i_world_model import IWorldModel


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# confidence decay per horizon step — far projection is less certain
_HORIZON_DECAY = 0.25
_LOW_CONF_WITHOUT_FACTS = 0.2


class ReferenceWorldModel(IWorldModel):
    """Rule-based transition model over WorldState.

    - `predict`: projects the action's effect onto world facts. Confidence starts
      from a base driven by how many world facts the action is GROUNDED in, then
      decays with `horizon` (0.25/step). With no relevant world facts the base is
      LOW (0.2) — prediction is essentially a guess.
    - `simulate`: one PredictedState per plan step (rollout); horizon grows along
      the rollout so later steps are less certain.
    - `evaluate`: predicted utility = predicted.confidence * intent-relevance of the
      projected facts (token overlap between intent and projected fact content).
    """

    def __init__(self, clock: NodeLamportClock) -> None:
        # ТЗ-RE-01 flag 1: predictions advance the SAME shared node clock, so the
        # predicted-state causal order matches kernel events + world facts.
        self._clock = clock

    def _grounding_base(self, world: WorldState, action: Action) -> float:
        """0..1 base confidence from how grounded the action is in current facts."""
        if not world.facts:
            return _LOW_CONF_WITHOUT_FACTS
        action_words = set(action.payload.lower().split())
        overlap = 0
        for content in world.facts.values():
            overlap += len(action_words & set(content.lower().split()))
        # at least one overlapping fact -> reasonable base; none -> low
        if overlap == 0:
            return 0.4
        return min(0.9, 0.5 + 0.1 * overlap)

    def predict(self, world: WorldState, action: Action, horizon: int = 1) -> PredictedState:
        horizon = max(1, int(horizon))
        base = self._grounding_base(world, action)
        conf = max(0.05, base * (_HORIZON_DECAY ** (horizon - 1)))
        # projected facts: carry over current facts + a projected effect of the action
        projected = dict(world.facts)
        projected[f"effect:{action.id}"] = action.payload
        causal: CausalMark = self._clock.tick()
        return PredictedState(
            id=_uid("pred"),
            horizon=horizon,
            projected_facts=projected,
            confidence=ConfidenceScore(conf, ProvenanceType.RULE_INFERENCE),
            causal=causal,
        )

    def simulate(self, world: WorldState, plan: Plan, horizon: int = 1) -> List[PredictedState]:
        states: List[PredictedState] = []
        roll_world = world
        step = 0
        for step_text in plan.steps:
            step += 1
            action = Action(id=f"{plan.id}-s{step}", kind="rule", payload=step_text,
                            confidence=plan.confidence, provenance=plan.provenance)
            # rollout horizon grows with step index: later steps = further = less certain
            st = self.predict(roll_world, action, horizon=horizon + step - 1)
            states.append(st)
            # feed the projection forward as the next rollout world
            roll_world = WorldState(node_id=world.node_id, facts=dict(st.projected_facts),
                                    confidence=st.confidence)
        return states

    def evaluate(self, predicted: PredictedState, intent: Intent,
                 values: Optional[IValueSystem] = None) -> float:
        intent_words = set(intent.text.lower().split())
        proj_text = " ".join(predicted.projected_facts.values()).lower()
        proj_words = set(proj_text.split())
        rel = len(intent_words & proj_words) / max(1, len(intent_words))
        # predicted utility = confidence * intent-relevance (0..1)
        return float(min(1.0, predicted.confidence.value * (0.5 + 0.5 * rel)))
