"""StigmergyStrategy — базовая стратегия координации (Phase C, Wave C1, ADR-103).

K1/K6: services импортирует только contracts + stdlib. Агенты НЕ вызывают друг друга
напрямую: writer пишет в IBlackboard (scope), reader читает snapshot (аудит #9).

Sequential / Hierarchical — СЛОТЫ, НЕ реализуются (аудит #3): добавлять, когда появится
реальный сценарий, требующий их.
"""

from __future__ import annotations

from typing import Tuple

from contracts.i_blackboard import BlackboardSnapshot
from contracts.i_coordination_strategy import CoordinationStep, ICoordinationStrategy


class StigmergyStrategy(ICoordinationStrategy):
    """Writer пишет в scope, reader читает snapshot; переход к следующему шагу по готовности."""

    @property
    def name(self) -> str:
        return "stigmergy"

    def next_step(
        self, prior: Tuple[CoordinationStep, ...], snapshot: BlackboardSnapshot
    ) -> CoordinationStep:
        # Базовая логика: если snapshot ещё пустой — ждём writer-а (он же writer_capability);
        # как только есть запись — следующий шаг = reader читает этот scope.
        last = prior[-1] if prior else None
        if last is not None and snapshot.version == 0:
            # ещё нет данных от writer — повторяем тот же scope (reader ждёт)
            return CoordinationStep(
                scope=last.scope,
                writer_capability=last.writer_capability,
                reader_capability=last.reader_capability,
            )
        # новый шаг: reader забирает scope, который заполнил writer
        scope = last.scope if last else snapshot.scope
        return CoordinationStep(
            scope=scope,
            writer_capability=last.writer_capability if last else "",
            reader_capability=last.reader_capability if last else "",
        )
