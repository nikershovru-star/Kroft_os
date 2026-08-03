"""Reflection Engine port (ТЗ-RF-01 / TZ-COG-005 / ADR-060) — K1-compliant.

Reflection is the ANALYTIC part of Self-Evolving (round 2 cognitive reflection): it
looks at accumulated experience (episodes + semantic + execution outcomes) and PROPOSES
evolution of the SOFT layer — it does NOT write memory. Memory Evolution (ТЗ-ME-01) is
the executive part that commits proposals under the O1 Self-Evolving guard.

Reflection addresses ФЛАГ 1 from ТЗ-ME-01: it is OUTCOME-BASED. Successful high-utility
experience is proposed for consolidation; repeated unsuccessful experience is proposed
for deprecation — rather than merely repeating intent text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from contracts.cognitive_domain import (
    ExecutionOutcome,
    ReflectionReport,
)
from contracts.i_cognitive_kernel import ILayeredMemory, IWorldState


class IReflectionEngine(ABC):
    """Metacognitive reflection over accumulated experience (ТЗ-RF-01).

    reflect() is pure analysis: it reads the layered memory + world + recent execution
    outcomes and returns a ReflectionReport of PROPOSALS. Committing those proposals
    (with the O1 Self-Evolving guard) is the job of Memory Evolution / the kernel's
    Learn phase — never Reflection itself.
    """

    @abstractmethod
    def reflect(self,
                memory: ILayeredMemory,
                world: IWorldState,
                recent_events: Optional[List[object]] = None,
                outcomes: Optional[List[ExecutionOutcome]] = None) -> ReflectionReport:
        """Analyse experience and propose SOFT-layer evolution.

        Args:
            memory: layered memory (episodes + semantic + normative).
            world: current world state (context for relevance).
            recent_events: recent CognitiveEvents (optional, for context).
            outcomes: execution outcomes (ФЛАГ 1 feedback proxy) — drives
                outcome-based consolidation/deprecation.

        Returns:
            ReflectionReport with consolidation/deprecation/policy candidates.
            MUST be empty (no candidates) when there is no experience to reflect on.
        """
        raise NotImplementedError
