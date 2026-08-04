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
    """Factory (Флаг C, standalone) — НЕ in build_kernel."""
    return ProcedureConsolidator(
        procedural, threshold=threshold, min_rate=min_rate, provenance=provenance
    )


class SkillEvolution:
    """Closed-loop skill lifecycle (ТЗ-SKILL-EVOLVE-01) — по образцу trust-эволюции ORCH-01.

    Feeds real dispatch outcomes back into a stored skill's confidence (success +, failure -),
    and INVALIDATES a skill when its confidence drops below a floor (repeated failures). After
    invalidation the orchestrator falls back to normal routing (agent/plugin). Deterministic (I-09)
    and SOFT (O1): only the skill's confidence/validity changes; HARD/FSM untouched.

    K5: переиспользует IProceduralMemory (record_skill_outcome / invalidate_skill) — НЕ дублирует
    порт/Procedure. Frozen Procedure обновляется как НОВАЯ версия (store_skill, idempotent).
    """

    def __init__(
        self,
        procedural: IProceduralMemory,
        delta: float = 0.1,
        invalidate_floor: float = 0.3,
    ) -> None:
        self._procedural = procedural
        self._delta = delta
        self._floor = invalidate_floor

    def on_skill_outcome(self, capability: str, success: bool) -> Optional["Procedure"]:
        """Record a skill-recall-dispatch outcome; evolve confidence, invalidate if too low.

        Returns the updated Procedure, or None if the skill was invalidated / did not exist.
        Deterministic (I-09): same inputs -> same confidence trajectory.
        """
        if not self._procedural.has_skill(capability):
            return None
        updated = self._procedural.record_skill_outcome(capability, success, self._delta)
        if updated is None:
            return None
        if updated.confidence < self._floor:
            self._procedural.invalidate_skill(capability)
            return None
        return updated


def build_skill_evolution(
    procedural: IProceduralMemory,
    delta: float = 0.1,
    invalidate_floor: float = 0.3,
) -> SkillEvolution:
    """Factory (Флаг C, standalone) — НЕ in build_kernel."""
    return SkillEvolution(procedural, delta=delta, invalidate_floor=invalidate_floor)

