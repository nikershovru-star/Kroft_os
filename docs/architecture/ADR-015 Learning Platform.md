---
tags: [kroft, adr, learning, architecture, wave12]
created: 2026-07-31
status: accepted
version: 1.0
updated: 2026-07-31
author: Hermes (senior software architect)
related:
  - "ADR-014 Agent Platform"
  - "ADR-012 Memory Platform"
  - "ADR-010 Evaluation Platform"
  - "ADR-013 Workflow Platform"
---

# ADR-015 — Learning Platform (Wave 12)

## Статус
**PROPOSED** — готов к реализации после approval.

## Контекст
Wave 11 (Agent Platform) выполняет задачи через Workflow → Router → LLM, но каждый
запуск начинается с чистого листа: система не помнит, что работало, а что нет.
Roadmap Wave 12 требует, чтобы система умела **анализировать собственную историю**.

Без этого Wave 13 (Optimization) не сможет давать рекомендации по выбору моделей/
маршрутов на основе фактов.

## Решение
Ввести три слоя:

1. **Сущность `ExecutionTrace`** (frozen, append-only) — неизменяемая запись одного
   прогона агента: `trace_id, goal, workflow_id, steps: Tuple[StepTrace,...],
   total_cost, total_latency_ms, final_status, timestamp, tags`.
   `StepTrace` несёт `step_id, model_id (actual_model), prompt, output, tools_used,
   cost, latency_ms, eval_score` (из Wave 7 через `Step.reflection_score`).

2. **Порт `ILearningStore`** — семантика *анализа*, не хранения (LAW 6):
   `record(trace)`, `query(pattern, limit)`, `aggregate(metric, group_by)`.
   Реализация `InMemoryLearningStore` — **обёртка** над `InMemoryMemoryStore`
   (Wave 9) с тегом `MemoryKind.LEARNING`. Хранилище не дублируем.

3. **Порт `IPatternExtractor`** — `extract(traces) → List[Pattern]`.
   `RuleBasedPatternExtractor` (v0.1) группирует по goal-категориям, сравнивает
   `avg_eval_score` по `model_id`, генерирует `Pattern` при разнице > 0.1.
   LLM-анализ — НЕ входит (Wave 13/14).

## Entities (из кода)
```python
@dataclass(frozen=True)
class StepTrace:
    step_id: str
    model_id: str
    prompt: str
    output: str
    tools_used: Tuple[str, ...] = ()
    cost: float = 0.0
    latency_ms: float = 0.0
    eval_score: float = 0.0

@dataclass(frozen=True)
class ExecutionTrace:
    trace_id: str
    goal: str
    workflow_id: str
    steps: Tuple[StepTrace, ...] = ()
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    final_status: str = ""
    timestamp: float = 0.0
    tags: Tuple[str, ...] = ()

@dataclass(frozen=True)
class Pattern:
    description: str
    confidence: float        # 0.0–1.0
    applies_to: Tuple[str, ...]
    recommendation: str
```

Ports:
```python
class ILearningStore(abc.ABC):
    def record(self, trace) -> None
    def query(self, pattern, limit=10) -> List[ExecutionTrace]
    def aggregate(self, metric, group_by) -> Dict[str, float]
    # metric: avg_latency | avg_cost | success_rate | avg_eval_score
    # group_by: model_id | provider | task_type

class IPatternExtractor(abc.ABC):
    def extract(self, traces) -> List[Pattern]
```

## Интеграция (Phase E)
`AgentPlatform.__init__` получает `learning_store: Optional[ILearningStore] = None`.
В конце `run()` строится `ExecutionTrace` из финального `Workflow` и вызывается
`learning_store.record(trace)`. Без `learning_store` поведение не меняется
(backward compatibility, существующие тесты Wave 11 не падают).

## Архитектурные законы (соблюдены)
- **LAW 1** — контракты (`contracts/i_learning.py`) до кода adapters/services.
- **LAW 2** — `AgentPlatform` импортирует только `contracts.ILearningStore`, не adapter.
- **LAW 3** — `ExecutionTrace`/`StepTrace`/`Pattern` frozen; `MemoryItem` immutable.
- **LAW 4** — каждый `Pattern` несёт `confidence` + `applies_to`.
- **LAW 5** — `aggregate()` возвращает числа, не догадки.
- **LAW 6** — `ILearningStore` имеет 1 реализацию (InMemory wrapper) в v0.1;
  вторая (SQLite/Analytics) — v0.5. Порт отделяет семантику анализа от хранения.
- **LAW 8** — новый Wave → новый ADR (этот).

## Consequences
- + Система накапливает историю прогонов и может её анализировать.
- + Wave 13 получает фактические данные (success_rate/avg_eval_score по model_id).
- − Добавление тега `MemoryKind.LEARNING` в `contracts/i_memory.py` (безопасное расширение).
- − `ExecutionTrace` сериализуется через `dataclasses.asdict` (не `trace.__dict__`,
  т.к. вложенные dataclass не JSON-сериализуемы).

## Отклонения от исходного спека (честный фикс)
1. `MemoryKind.LEARNING` добавлен в `contracts/i_memory.py` (в спеке erroneously
   предполагался существующим).
2. Сериализация trace → `json.dumps(dataclasses.asdict(trace))` + реконструкция
   `ExecutionTrace(**d, steps=tuple(StepTrace(**s) for s in d["steps"]))`.
   Прямой `json.dumps(trace.__dict__)` ломается на Tuple[StepTrace].

## Следующий шаг
Wave 13 — Optimization Platform (Recommendation → Shadow Mode → Canary → Approval →
Rollback). НЕ начинать без явной команды.
