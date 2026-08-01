---
tags: [kroft, adr, agent, architecture, wave11]
created: 2026-07-31
status: accepted
version: 1.0
updated: 2026-07-31
author: Chief Knowledge Architect (Hermes)
related:
  - "ADR-010 Evaluation Platform"
  - "ADR-011 Knowledge Platform"
  - "ADR-012 Memory Platform"
  - "ADR-013 Workflow Platform"
  - "ADR-005 Policy Platform"
summary: >-
  Agent Platform = платформенный слой оркестрации (Wave 11), связывающий существующее
  agent-ядро (Stage 33) с платформами волн 5–10. IAgentPlatform.run(goal) -> frozen
  AgentResult (traceable: goal, workflow, memory_refs, knowledge_hits, eval_summary,
  route_log, tool_results). Зависит только от contracts (LAW 2).
---

# ADR-014 — Agent Platform (Wave 11)

**Status:** accepted (Wave 11 реализован: коммиты `aa3196d` порты, `b5f115f` оркестратор,
`a31d6a3` тесты, `ea1de10` регистрация портов; 15 passed на `tests/test_agent_platform*.py`,
арх-гейт без новых нарушений — `agent_platform.py` импортирует только `contracts.*`)
**Wave:** 11

---

## 1. Context

Roadmap (Stage 4 — Agents, Wave 11–12):

> **Wave 11 — Agent Platform:** `Аgent = Planner + Memory + Knowledge + Tools + Workflow + Policies + LLM + Evaluator`

К моменту Wave 11 в репозитории **уже есть** agent-ядро — это не волна построила его с
нуля, он появился раньше, вне волн-фреймворка:

- `contracts/agent.py` — `IAgent` (порт) + `Tool` (датакласс).
- `services/tool_registry.py` — `ToolRegistry` (регистрация/вызов инструментов).
- `services/agent_service.py` — `АgentService`, **1106 строк**, rule-based intent-роутер
  (Stage 33/34 + десяток последующих стейджей). 30+ тестов (`test_agent*.py`).
- `adapters/agent_adapter.py` — `RuleBasedАgentAdapter`, приводит `АgentService` к `IAgent`.

Этот сервис **автономен**: он матчит натуральный язык в цепочку вызовов инструментов графа,
но **не знает** про Workflow (10), Memory (9), Knowledge (8), Evaluation (7), Policy (5).
Он не планирует через `RuleBasedPlanner`, не бежит через `WorkflowExecutor`, не пишет в
`MemoryPlatform`, не читает `KnowledgePlatform`, не измеряется `EvaluationPlatform`.

Поэтому Wave 11 — **не постройка агента заново**, а постройка **Platform-слоя оркестрации**,
который делает существующее ядро (и недостающие платформы) частями одной системы. Это тот же
смысл слова «Platform», что в Wave 3-10: тонкий координатор поверх портов, а не ещё one more
монолит.

> **Осознанное решение (не дублировать).** Переписывать `АgentService` — значит сломать 30+
> тестов и нарушить закон «не ломай фундамент». Wave 11 добавляет `IAgentPlatform` + оркестратор,
> который принимает готовые подсистемы **инъекцией** (composition root), не импортируя сиблинг-
> сервисы. Существующий `АgentService` остаётся нетронутым и продолжает жить своими тестами.

## 2. Decision

### 2.1 Definition of Done (Roadmap)

> Агент = связка Planner + Memory + Knowledge + Tools + Workflow + Policies + LLM + Evaluator.

Формализуется в порт `IAgentPlatform.run(goal) -> AgentResult`, где `АgentResult` несёт:

| Поле | Откуда |
|------|--------|
| `goal` | вход |
| `workflow` | `Workflow` (Wave 10), собранный `RuleBasedPlanner` |
| `status` | `done` / `failed` (как у Workflow) |
| `memory_refs` | ключи записей Session/Long-Term (Wave 9) |
| `knowledge_hits` | факты из графа (Wave 8), если искали |
| `eval_summary` | `Scorecard`-метрики (Wave 7), если измеряли |
| `route_log` | какие модели выбрал PolicyEngine (Wave 5) |
| `tool_results` | что вернули инструменты (ToolRegistry / АgentService) |

### 2.2 Сущность

`АgentResult` — **frozen** (как `Workflow`/`Step` в Wave 10): состояние меняется явно через
copy-on-write, воспроизводимость сохраняется. Полей времени **нет** (тот же аргумент, что в
Wave 10: тайминг — в `Scorecard`).

### 2.3 Порты (`contracts/i_agent_platform.py`)

```python
class IАgentPlatform(abc.ABC):
    @abc.abstractmethod
    def run(self, goal: str, context: PolicyContext | None = None) -> АgentResult: ...
```

Оркестратор (`services/agent_platform.py`) зависит **только от контрактов** (LAW 2). Все
конкретные подсистемы приходят через конструктор:

| Зависимость | Тип инъекции | Откуда |
|-------------|--------------|--------|
| planner | `IPlanner` (порт) | Wave 10 `RuleBasedPlanner` |
| executor | `IExecutor` (порт) | Wave 10 `WorkflowExecutor` |
| memory | объект (метод `remember_turn`/`build_context`) | Wave 9 `MemoryPlatform` |
| knowledge | объект (метод `facts`/`find`) | Wave 8 `KnowledgePlatform` |
| evaluator | объект (метод `run`/`record`) | Wave 7 `EvaluationPlatform` |
| policies | `PolicyEngine` (или `None`) | Wave 5 |
| tools | `ToolRegistry` **или** `IAgent` | Stage 33 / сущ. ядро |

`test_services_do_not_cross_import` запрещает `from services.X import ...` внутри сервиса,
поэтому `agent_platform.py` **не импортирует** `workflow_executor`, `memory_platform`,
`knowledge_platform`, `evaluation_platform`, `policy_engine`, `agent_service`. Они собираются
в composition root (CLI/main) и передаются как аргументы. Сам оркестратор импортирует лишь
`contracts.*`.

### 2.4 Поток выполнения

```
goal
  │
  ▼
IAgentPlatform.run(goal)
  │  1. planner.plan(goal)            -> List[Step]        (Wave 10)
  │  2. собрать Workflow(id, goal, plan)
  │  3. executor.execute(wf, router)  -> Workflow завершён  (Wave 10)
  │       router = policies-маршрут (Wave 5/6)
  │  4. Memory: записать goal+итог в Session/Long-Term     (Wave 9)
  │  5. Knowledge: опц. поиск фактов по goal               (Wave 8)
  │  6. Evaluation: опц. измерить итог через Scorecard      (Wave 7)
  │  7. Tools: опц. делегировать инструментальную часть    (Stage 33)
  │
  ▼
АgentResult(goal, workflow, memory_refs, knowledge_hits, eval_summary, route_log, tool_results)
```

**Tools — не замена планировщику.** `АgentService` умеет матчить NL в цепочку инструментов графа;
`IAgentPlatform` использует его как **один из обработчиков** для инструментальных подзадач
(«найди дубликаты в графе»), а для когнитивных («объясни влияние X») — Workflow через LLM.
Разделение ответственности, а не конкуренция.

### 2.5 Границы слоёв (LAW 1 / LAW 2)

```
contracts/i_agent_platform.py  → stdlib + contracts (i_workflow, i_policy, i_llm, i_memory, i_eval)
services/agent_platform.py     → contracts only (НИКОГДА adapters/сиблинг-сервисы)
```

В отличие от Wave 10, здесь **нет** composition-root модуля внутри `services/`: инъекция
происходит снаружи (CLI), потому что зависимостей много и они разнородны. `agent_platform.py`
остаётся «чистым» оркестратором, годным и для тестов (моки), и для продакшена (реальные сервисы).

## 3. v0.1 ограничения (осознанные)

| Область | v0.1 | Дальше |
|---------|------|--------|
| Планировщик | rule-based (Wave 10) | LLM-планировщик (Wave 12) |
| Интеграция Tools | делегирование `IAgent`/ToolRegistry | нативный tool-calling через LLM |
| Knowledge | опциональный поиск по goal | авто-подстановка фактов в prompt |
| Evaluation | опциональный `Scorecard` | обязательное измерение каждого шага |
| Orchestration | последовательная | DAG-планирование из Wave 10 v1.0 |

## 4. Consequences

**Плюсы**
- Агент становится first-class частью системы волн 5-10, не дублируя существующее ядро.
- `АgentResult` несёт полный след: что спланировано, через кого выполнено, что запомнено,
  что извлечено из знаний, как измерено — трассируемость по LAW 4.
- Существующие 30+ тестов `АgentService` не трогаются.

**Минусы / долг**
- `АgentService` (Stage 33) всё ещё вне волн-фреймворка; его миграция под `IAgentPlatform`
  — отдельная задача (v1.0), не ломающая текущий код.
- `agent_adapter.py` импортирует `contracts.IAgent` — чист; но если когда-то потребуется
  прямой импорт `services.agent_service`, арх-гейт это заблокирует (уже учтено: type-hint
  оставлен строковым).

## 5. Проверка (Phase G)

- `tests/test_agent_platform_contract.py` — порт абстрактен, `АgentResult` frozen.
- `tests/test_agent_platform.py` — моки всех подсистем: run собирает Workflow, пишет в Memory,
  читает Knowledge, измеряет через Evaluation, делегирует Tools.
- `tests/test_agent_platform_live.py` — gated `AGENT_LIVE=1`: реальный goal через собранные
  сервисы + OmniRoute.

## 6. Связанные решения

- ADR-005 Policy — выбор маршрута для шагов агента.
- ADR-010 Evaluation — `Scorecard` как вход измерения.
- ADR-011 Knowledge — факты как источник контекста.
- ADR-012 Memory — Session/Long-Term как память агента.
- ADR-013 Workflow — план агента как `Workflow`.
