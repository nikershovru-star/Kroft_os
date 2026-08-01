---
tags: [kroft, adr, workflow, architecture, wave10]
created: 2026-07-31
status: accepted
---

# ADR-013 — Workflow Platform (Wave 10)

**Status:** accepted
**Wave:** 10
**Commits:** `565e4f4` (ports) · `4f8fc1b` (planner) · `7e5c2ad` (executor+reflection+retry) · `01780c9` (tests)
**Verification:** 30 pa...[truncated]

---

## 1. Context

К концу Wave 9 собраны все подсистемы: маршрутизация (6), измерение (7), знания (8),
память (9). Но каждый вызов — ручной: кто-то снаружи должен решить, какие шаги сделать,
в каком порядке, что делать при плохом ответе. Задача существует только в голове вызывающего
и исчезает вместе со стеком вызовов.

Правило Roadmap:

> Любая задача — это **Workflow**. Не цепочка вызовов функций.

Разница принципиальная. Цепочка вызовов — это код: её нельзя сохранить, показать, повторить
или объяснить. Workflow — это **данные**: его можно сериализовать, положить в память,
воспроизвести и предъявить как доказательство того, что и почему произошло.

## 2. Decision

### 2.1 Definition of Done

> Любой Workflow можно сохранить, повторить и воспроизвести.

Формализуется в три проверяемых свойства:

| Свойство | Проверка |
|----------|----------|
| **Сохраняемость** | `asdict(wf)` → `json.dumps` без потерь |
| **Восстановимость** | `Workflow(**json.loads(...))` даёт эквивалентный объект |
| **Воспроизводимость** | два прогона на одних входах дают идентичный JSON |

Из третьего следует важное **отрицательное** решение: в `Step` **нет полей времени**
(`timestamp`, `duration_ms`). Любая метка времени сделала бы два прогона неравными и убила бы
DoD. Тайминг — забота Evaluation (Wave 7), он живёт в `Scorecard`, не в workflow.

### 2.2 Сущности

`Step` — единица работы. Все поля скалярные, объект **frozen**.
`Workflow` — first-class entity: `id`, `goal`, `plan`, `variables`, `status`, `reflection_log`.
Тоже **frozen**; изменение состояния — через copy-on-write (`with_step`, `with_status`).

> **Расхождение со спекой волны (исправлено осознанно).** Phase B описывает `Workflow`
> и `Step` как обычные `@dataclass` (mutable), но Phase G требует тест «Workflow/Step frozen»,
> а LAW 3 — «состояние меняется явно через `replace()`». Спека противоречит сама себе.
> Выбран frozen + copy-on-write: он удовлетворяет и Phase G, и LAW 3, и делает
> воспроизводимость доказуемой. Мутабельный вариант удовлетворял бы только Phase B.

**Компромисс по `variables`.** Внутри frozen-датакласса `Dict` остаётся мутабельным
(та же ловушка, что с `Fact.history` в Wave 8 и `MemoryItem.tags` в Wave 9). Здесь он
**сознательно оставлен словарём**, а не кортежем пар: JSON-форма `{"k": "v"}` пригодна для
чтения и ручной правки, а `[["k","v"]]` — нет, и DoD «сохранить/повторить» пострадал бы
в первую очередь. Защита: `__post_init__` берёт **копию** переданного словаря (внешняя
мутация не протекает), а все обновления идут через `with_variables()`, которая копирует.
Это единственный не-глубоко-замороженный контейнер в волне, и он документирован здесь.

### 2.3 Порты (`contracts/i_workflow.py`)

| Порт | Ответственность |
|------|-----------------|
| `IPlanner` | `plan(goal, context) -> List[Step]` — разложить цель на шаги |
| `IExecutor` | `execute(workflow, router) -> Workflow` — выполнить план |
| `IReflection` | `evaluate_step(step, scorecard) -> bool` — приемлем ли результат |
| `IRetryManager` | `should_retry(step)` + `prepare_retry(query, context, attempt)` |

**`IScheduler` порт НЕ создаётся.** Phase A перечисляет его среди портов, но Phase D тут же
уточняет: «v0.1 не нужен отдельный порт, Scheduler — логика внутри Executor», и в списке
коммитов `services/scheduler.py` отсутствует. Порт с одной тривиальной реализацией
(«выполняй по порядку») нарушил бы LAW 6. Последовательный порядок — цикл внутри executor;
DAG-планирование появится в v1.0 вместе со второй реализацией.

**`router` — структурный порт, не класс.** Phase B в сигнатуре `IExecutor.execute` указывает
`router: Router`, но `Router` живёт в `adapters/`, а executor — в `services/`; импорт нарушил бы
LAW 2 и уронил арх-гейт. Используется `RouterFn = Callable[[ModelQuery], LlmResponse]` — тот же
приём, что в `IBenchmark` (Wave 7) и `LLMEntityExtractor` (Wave 8).

### 2.4 Правило интеграции

```
goal ──► Planner ──► plan[Step]
             │
             ▼
        Executor ─── для каждого шага ───┐
             │                            │
   Memory (9) даёт контекст               │
   Router (6) выполняет   ────────────────┤
   Reflection (7) оценивает               │
   RetryManager (5) меняет маршрут ◄──── fail
             │
             ▼
     Workflow (done / failed) + reflection_log
```

**Retry ≠ повтор того же.** Менеджер не перезапускает идентичный запрос — он меняет
`PolicyContext.tags` и флаги `ModelQuery`, чтобы `PolicyEngine` (Wave 5) выбрал **другой**
маршрут. Попытка 2 → `reasoning=True`, попытка 3 → `local=True`. Иначе retry — это просто
трата бюджета на тот же результат.

### 2.5 Границы слоёв (LAW 1 / LAW 2)

```
contracts/i_workflow.py       → stdlib + contracts (i_llm, i_policy, i_eval)
adapters/rule_based_planner.py → contracts
services/workflow_executor.py  → contracts     (НИКОГДА adapters/сиблинг-сервисы)
services/reflection.py         → contracts
services/retry_manager.py      → contracts
```

`test_services_do_not_cross_import` запрещает `from services.X import ...` внутри сервисов.
Поэтому `WorkflowExecutor` **не импортирует** `reflection.py`/`retry_manager.py` — они
приходят инъекцией как `IReflection` / `IRetryManager`. Сборка — в composition root.

## 3. v0.1 ограничения (осознанные)

| Область | v0.1 | Дальше |
|---------|------|--------|
| Planner | rule-based, keyword matching | LLM-планировщик (Wave 11) |
| Scheduler | sequential | DAG с зависимостями (v1.0) |
| Reflection | эвристика: непустой output > 20 символов | rubric + LLM-judge (v1.0) |
| Retry | 3 попытки, смена флагов запроса | учёт причины отказа (v1.0) |
| Persistence | JSON-строка | хранение в Memory Platform (v1.0) |

Reflection v0.1 честно называется эвристикой: она отличает «пусто/обрубок» от «что-то есть»,
и не притворяется, что судит смысл. Но `reflection_score` **записывается всегда** (LAW 5) —
без накопленных чисел не с чем будет сравнивать v1.0.

## 4. Consequences

**Плюсы**
- Задача становится данными: сохраняется, воспроизводится, предъявляется.
- Каждый шаг несёт `route_used`, `attempts`, `reflection_score` — трассируемость по LAW 4.
- Executor не знает ни про Router, ни про конкретную рефлексию: подмена — вопрос инъекции.

**Минусы / долг**
- `variables` — единственный не замороженный контейнер (осознанный компромисс, см. §2.2).
- Rule-based планировщик не поймёт цель вне ключевых слов — уйдёт в `default`-план.
- Sequential-исполнение не использует параллелизм независимых шагов (ждёт DAG).
- Reflection-эвристика пропустит связный, но неверный по смыслу ответ.

## 5. Проверка (Phase G)

- `tests/test_workflow_contract.py` — порты абстрактны, `Workflow`/`Step` frozen, JSON round-trip.
- `tests/test_rule_based_planner.py` — keyword → ожидаемый набор шагов.
- `tests/test_workflow_executor.py` — моки: успех, отказ рефлексии, retry со сменой маршрута.
- `tests/test_workflow_integration.py` — Planner + Router + PolicyEngine + Memory + Reflection.
- `tests/test_workflow_live.py` — gated `WORKFLOW_LIVE=1`: двухшаговый workflow через OmniRoute.

## 6. Связанные решения

- ADR-009 Policy — `PolicyContext.tags` как рычаг смены маршрута при retry.
- ADR-010 Evaluation — `Scorecard` как вход рефлексии.
- ADR-011 Knowledge — шаг `fact_check` может обращаться к графу фактов.
- ADR-012 Memory — Session Memory даёт контекст шагу, Long-Term хранит результат.
