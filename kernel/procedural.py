"""Reference procedural-memory consolidator (ТЗ-SKILL-01, ADR-074) — deterministic, LLM-free.

K5 (commit 0): НЕ дублирует существующий IProceduralMemory (contracts/i_memory.py, Wave 9/ADR-012)
и НЕ дублирует cognitive_domain.Skill (Marketplace). Переиспользует IProceduralMemory (роль
процедурной памяти) + Procedure VO. ORCH-01 ActionLog/TaskOutcome — источник исходов (через
явный learn()-вход, НЕ мутируя ActionLog).

K1: kernel + contracts only. O1: Procedure — SOFT (не мутирует HARD/FSM). I-09: консолидация
детерминирована (порог N + success-rate; первые успешные steps фиксируются детерминированно,
skill_id = f"skill:{capability}"). Флаг C: build_procedural — standalone, НЕ в build_kernel.
"""

from __future__ import annotations

from contracts.i_memory import IProceduralMemory, Procedure
from dataclasses import dataclass


@dataclass(frozen=True)
class _Attempt:
    steps: tuple
    success: bool


class ProcedureConsolidator:
    """Consolidates repeated successful executions into reusable Procedures (skills).

    Deterministic (I-09): for a given capability, once ``success_count >= threshold``
    (and the success rate is >= ``min_rate``), a single Procedure is written via
    ``procedural.store_skill`` exactly once (idempotent: skipped if already present).
    The steps of the FIRST successful attempt are used — stable across call orders.
    """

    def __init__(
        self,
        procedural: IProceduralMemory,
        threshold: int = 3,
        min_rate: float = 0.8,
        provenance: str = "procedure_consolidator",
    ) -> None:
        self._procedural = procedural
        self._threshold = threshold
        self._min_rate = min_rate
        self._provenance = provenance
        self._attempts: dict[str, list[_Attempt]] = {}

    def learn(self, capability: str, steps, success: bool, causal: str | None = None) -> None:
        """Record one execution outcome; consolidate a Procedure when the bar is met."""
        if capability not in self._attempts:
            self._attempts[capability] = []
        self._attempts[capability].append(_Attempt(tuple(steps), bool(success)))
        self._maybe_consolidate(capability, causal)

    def _maybe_consolidate(self, capability: str, causal: str | None) -> None:
        if self._procedural.has_skill(capability):
            return  # already consolidated (idempotent)
        attempts = self._attempts[capability]
        successes = [a for a in attempts if a.success]
        if len(successes) < self._threshold:
            return
        rate = len(successes) / float(len(attempts))
        if rate < self._min_rate:
            return
        first_steps = successes[0].steps
        skill = Procedure(
            skill_id=f"skill:{capability}",
            name=capability,
            capability=capability,
            steps=first_steps,
            preconditions=(),
            confidence=round(rate, 3),
            provenance=self._provenance,
            causal=causal,
        )
        self._procedural.store_skill(skill)

    def known_skills(self) -> list[Procedure]:
        return self._procedural.list_skills()


def build_procedural(
    procedural: IProceduralMemory,
    threshold: int = 3,
    min_rate: float = 0.8,
    provenance: str = "procedure_consolidator",
) -> ProcedureConsolidator:
    """Factory (Флаг C, standalone) — НЕ в build_kernel."""
    return ProcedureConsolidator(
        procedural, threshold=threshold, min_rate=min_rate, provenance=provenance
    )
