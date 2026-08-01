---
tags: [kroft, adr, evaluation, architecture, wave7]
created: 2026-07-31
status: accepted
depends: [ADR-006, ADR-009]
closes: [Wave 7]
---

# ADR-010 — Evaluation Platform (Wave 7)

> Статус: **proposed** → после реализации и тестов → accepted.
> Зависит от: ADR-006 (Model Platform), ADR-009 (Policy Platform).
> Закрывает: Wave 7 целиком.

## 1. Контекст и мотивация

Wave 6 (`Router`) умеет **выбирать** модель. Но выбор — это эвристика:
`ProviderSelectionPolicy` считает `score` из `latency/quality/cost`, где
`quality` — бинарная эвристика (`reasoning ? 1.0 : 0.7`). Система не знает,
*почему* выбран именно этот вариант и *насколько он хорош*.

Без Evaluation: Routing = эвристика.
После Evaluation: Routing = **доказуемое решение** (LAW 4: Decision → Evidence → Explanation).

Wave 7 вводит **Evaluation Platform** — слой измерения качества моделей и
маршрутизации на основе измеренных, а не предполагаемых, метрик.

## 2. Принцип: Measurement over Assumption

- Модель оценивается на **immutable Golden Dataset** (5 категорий).
- Каждый прогон оставляет **Scorecard** (Input/Model/Output/Metric/Evidence).
- `ProviderSelectionPolicy` v2 подмешивает `scorecard.accuracy` к эвристике —
  но эвристика НЕ удаляется (обратная совместимость, работа без scorecard).
- Никакое решение не автоматизируется без измерения/воспроизведения/объяснения
  (LAW 5).

## 3. Архитектурные границы (LAW 1/2)

```
contracts/i_eval.py        (ports + entities, НЕТ реализации)
        │
services/evaluation_platform.py   (BenchmarkRunner, MetricsCollector) — зависит ТОЛЬКО от contracts
        │                                   │
        └── НЕ импортирует adapters ────────┘  (LAW 2: services → adapters ЗАПРЕЩЁН)
```

`BenchmarkRunner` **не** принимает конкретный `Router` (нарушило бы LAW 2:
services→adapters). Вместо этого он принимает `router: Callable[[ModelQuery], LlmResponse]`
— структурный, а не nominal, порт. `Router` (adapters) ему соответствует.
Это намеренно НЕ новый `IRouter` port (LAW 6: одна реализация ≠ новая абстракция).

Golden Dataset immutable: любое изменение = ADR + commit + reason (как в Roadmap).

## 4. Core Abstractions (порты)

### 4.1 Entities
- `Task` — immutable: id, category (QA/Reasoning/Summarization/EntityExtraction/Retrieval),
  input, expected (optional, для точных метрик), rubric (опц.).
- `Metric` — имя + значение + единица (accuracy/latency_ms/cost/stability/
  success_rate/explainability_score).
- `Scorecard` — aggregate результата прогона: task_id, model_id, output,
  metrics: Dict[str, float], evidence: str, decision_trace: Optional[str].

### 4.2 IEvaluator
`evaluate(task, response) -> Dict[str, float]` — считает метрики по паре
(task, model output). Pure function, no I/O, no hidden state (LAW 3).

### 4.3 IBenchmark
`run(task, router) -> Scorecard` — прогон одной задачи через `router`
(callable), сбор метрик через IEvaluator, сохранение Scorecard.

### 4.4 IScorecard
`record(scorecard)` / `fetch(task_id, model_id) -> Optional[Scorecard]` /
`leaderboard(model_id) -> float` (агрегированная accuracy). Это storage-порт
scorecard'ов; v0.1 реализация — in-memory + опц. json через IFileSystem.
(Хранение состояния — явный объект, не global, LAW 3.)

## 5. Реализация (фазы)

- **A** `contracts/i_eval.py` — порты + entities.
- **B** `services/evaluation_platform.py` — `BenchmarkRunner` (IBenchmark),
  `MetricsCollector` (IEvaluator, реализует все 6 метрик), `InMemoryScorecard`
  (IScorecard). Зависит только от contracts.
- **C** `services/golden_dataset.py` — immutable `GOLDEN_DATASET: List[Task]`
  (5 категорий, ≥1 пример каждой), `fetch_dataset() -> Tuple[List[Task], ...]`.
- **D** метрики: accuracy (exact/substring/LLM-judge-заглушка v0.1),
  latency (из LlmResponse.latency_ms), cost (из LlmResponse.cost),
  stability (дисперсия по N прогонам), success_rate (ok()),
  explainability_score (есть ли decision_trace).
- **E** `ProviderSelectionPolicy` v2 — `_score` добавляет
  `accuracy_weight * scorecard.leaderboard(model.id)` если scorecard доступен;
  иначе чистая эвристика. Объяснимо: audit_log несёт `acc=...`.

## 6. Интеграции

- С Registry (Wave 4): scorecard агрегируется по `model.id`.
- С Policy (Wave 5): `ProviderSelectionPolicy` читает scorecard в фазе ranking.
- С Router (Wave 6): `BenchmarkRunner` вызывает `router(query)` как callable.
- С Audit: каждый Scorecard несёт `evidence` + `decision_trace`.

## 7. Чек-лист реализации

- [ ] contracts/i_eval.py — IEvaluator, IBenchmark, IScorecard, Task, Metric, Scorecard
- [ ] services/evaluation_platform.py — BenchmarkRunner, MetricsCollector, InMemoryScorecard
- [ ] services/golden_dataset.py — 5 категорий, immutable
- [ ] metrics: accuracy, latency, cost, stability, success_rate, explainability_score
- [ ] policies/provider_selection_policy.py — v2 scorecard blend
- [ ] tests/test_eval_contract.py — порты
- [ ] tests/test_evaluation_platform.py — BenchmarkRunner + MetricsCollector
- [ ] tests/test_eval_integration.py — Router + Registry + Policy + Evaluation (offline)
- [ ] contracts/__init__.py — регистрация портов
- [ ] ADR-010 → accepted после review

## 8. Решение (почему так, а не иначе)

- **Не создаём IRouter port** (LAW 6): одна реализация Router. Callable-порт
  достаточен и не ломает LAW 2.
- **Scorecard storage отделён** (LAW 3): явный IScorecard, не global dict.
- **Эвристика сохраняется** (LAW 5 + обратная совместимость): scorecard —
  надстройка, система работает и без него.
- **Golden Dataset immutable**: меняется только через ADR (как требует Roadmap).
