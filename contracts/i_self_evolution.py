"""Self-Evolution behavioral-closure contracts (ТЗ-SE-01, ADR-064).

K1-compliant: stdlib + contracts only. LLM-FREE core (reference sources).

ТЗ-SE-01 closes ФЛАГ 3 (ТЗ-EX-01): deliberation (reasoning / value-system) reads the
EVOLVED SOFT layer (semantic facts + soft policies) so that self-evolution changes
BEHAVIOR, not just memory.

Design (no signature break of IValueSystem / IReasoningEngine):
- IValueSystem and IReasoningEngine keep their existing abstract methods.
- A NEW port `ISoftPolicySource` exposes the evolved SOFT layer to deliberation:
  * prefer / avoid patterns (from soft normative policies, layer=="soft")
  * recall facts (from consolidated semantic facts, e.g. "decided:<action>")
- Reference impls (kernel/self_evolution.py) read these from ILayeredMemory through
  this port, so deliberation stays K6-clean (services -> adapters via ports).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class SoftPolicyPreference:
    """A single SOFT-layer preference derived from evolution.

    kind: "prefer" raises score of matching candidates; "avoid" lowers it.
    pattern: substring matched against candidate plan steps / descriptions.
    weight: signed strength (prefer > 0, avoid < 0).
    """
    pattern: str
    kind: str          # "prefer" | "avoid"
    weight: float = 0.0


class ISoftPolicySource(ABC):
    """Port exposing the EVOLVED SOFT layer to deliberation (ТЗ-SE-01).

    Implementations read ILayeredMemory (get_normative soft + get_semantic) — they
    never mutate it. This is the read-side closure of the Self-Evolving loop:
    outcomes -> reflection -> memory evolution -> [THIS PORT] -> deliberation reads
    learned layer -> decisions change -> new outcomes.
    """

    @abstractmethod
    def get_prefer_patterns(self) -> List[str]:
        """Substrings that SHOULD be favored in candidate selection."""
        ...

    @abstractmethod
    def get_avoid_patterns(self) -> List[str]:
        """Substrings that SHOULD be penalized in candidate selection."""
        ...

    @abstractmethod
    def get_recall_facts(self) -> List[str]:
        """Consolidated 'decided:<action>' facts to surface as candidate directions."""
        ...

    # ---- convenience aggregation (default, overridable) --------------------
    def get_preferences(self) -> List[SoftPolicyPreference]:
        prefs: List[SoftPolicyPreference] = []
        for p in self.get_prefer_patterns():
            prefs.append(SoftPolicyPreference(pattern=p, kind="prefer", weight=1.0))
        for p in self.get_avoid_patterns():
            prefs.append(SoftPolicyPreference(pattern=p, kind="avoid", weight=-1.0))
        return prefs
