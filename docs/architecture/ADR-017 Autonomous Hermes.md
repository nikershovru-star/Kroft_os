---
tags: [kroft, adr, autonomy, architecture, wave14]
created: 2026-07-31
status: accepted
version: 1.0
updated: 2026-07-31
author: Hermes (senior software architect)
summary: >-
  Wave 14 Autonomous Hermes: замыкает цикл observe-learn-optimize-act.
  Агент самостоятельно инициирует ретроспективу, оценивает качество своих
  решений, поддерживает документацию в актуальном состоянии и может
  предлагать оптимизации через LLM — но никогда не применяет их без явного
  approve (ConfigApplier Wave 13).
related:
  - "ADR-016 Optimization Platform"
  - "ADR-015 Learning Platform"
  - "ADR-014 Agent Platform"
---

# ADR-017 — Autonomous Hermes (Wave 14)

## Статус
**PROPOSED** — готов к реализации после approval. Черновик от пользователя
доработан по результатам сверки с фактическими контрактами Wave 11–13
(см. «Корректировки по фактическому коду»).

## Контекст
Wave 11–13 построили замкнутый pipeline: `AgentPlatform` → Learning (Trace/Pattern)
→ Optimization (Recommendation → Guardrail → ConfigApplier). Но триггеры — внешние
(human command). Wave 14 вводит **внутренний цикл**: агент сам решает, когда
провести ретроспективу, и сам поддерживает свою документацию. Это финальная
волна KROFT_OS Roadmap.

Риск: автономия легко превращается в неуправляемую автоматику. Жёсткий guardrail:
**mutation только через `ConfigApplier` с двухфазным commit** (Wave 13). Никакой
компонент Wave 14 не вызывает `apply()` напрямую.

## Решение
Четыре компонента + один неготируемый инвариант.

### 1. IAutonomyController (порт)
`should_retrospect(traces: List[ExecutionTrace], config: Dict) -> bool` — решает,
накопилось ли достояние evidence для самоанализа. Реализация
`ThresholdAutonomyController`: срабатывает при `len(traces) >= N` ИЛИ
`time_since_last > T` (rate-limit: max 1 ретроспектива в час — защита от loop
autonomy).

### 2. ISelfEvaluator (порт)
`evaluate(traces: List[ExecutionTrace], patterns: List[Pattern]) -> EvaluationReport`.
Метрики (считаются СTIРОГО по фактическим полям Wave 12, см. Корректировки):
- `plan_success_rate` — доля `ExecutionTrace` с `final_status == "done"`.
- `pattern_drift` — отношение applied-рекомендаций к rolled_back (через
  `ConfigApplier.status(rec_id)`).
- `optimization_yield` — доля рекомендаций, дошедших до `approved`/`applied`.

Продуцирует `EvaluationReport` (frozen). Не трогает runtime.

### 3. IDocMaintainer (порт)
`sync(docs_root: str, code_state: Dict) -> DocSyncResult`. Проверяет (READ-ONLY):
- ADR-статусы соответствуют коду (ADR-016 `accepted`, а `ConfigApplier` отсутствует — mismatch);
- MOC-ссылки резолвятся (файлы существуют);
- Roadmap-статусы и хэши коммитов актуальны;
- Build Journal содержит секции для всех закрытых волн.

Только **проверяет и предлагает diff** (`proposed_diffs`), не пишет в файлы без approve.

### 4. LlmOptimizer (АДАПТЕР IOptimizer, не новый порт)
Второй `IOptimizer`, регистрируется параллельно `PatternBasedOptimizer` в
`AgentPlatform.optimizer: Optional[IOptimizer]`. Принимает `patterns` и
`current_config`, формирует prompt для LLM, парсит `Recommendation`. Ограничения:
- `confidence` выставляется LLM (0.0–1.0), но порог `MIN_CONFIDENCE = 0.7` (LAW 5);
- `target` — только из whitelist путей (`policy:`, `knowledge:`);
- `value` — JSON-строка, scalar или dict, НЕ executable code;
- обязательно проходит через `IGuardrail` перед попаданием в `ConfigApplier`.
`PatternBasedOptimizer` остаётся fallback (если LLM недоступен).

### 5. Инвариант (неготируемый)
**Никакой компонент Wave 14 не вызывает `ConfigApplier.apply()` напрямую.** Только
`propose()` → human / Wave-14-orchestrator → `approve()` → `apply()`.

## Entities (предварительные)
```python
@dataclass(frozen=True)
class EvaluationReport:
    timestamp: str
    plan_success_rate: float
    pattern_drift: float
    optimization_yield: float
    attention: Tuple[str, ...]   # id рекомендаций, требующих внимания

@dataclass(frozen=True)
class DocSyncResult:
    mismatches: Tuple[str, ...]
    proposed_diffs: Tuple[str, ...]
```

## Архитектурные законы (соблюдены)
- **LAW 1** — контракты (`contracts/i_autonomy.py`) до кода.
- **LAW 2** — порты импортируют только `contracts.*` (и stdlib). Никаких
  `import services.*` в портах.
- **LAW 3** — `EvaluationReport`/`DocSyncResult` frozen. Состояние автономии
  (счётчики, `last_retrospect_at`) — явное mutable state в `AutonomyController`,
  не глобальное.
- **LAW 4** — `EvaluationReport` содержит `timestamp` + список трейсов (через
  `len(traces)` в отчёте / явную ссылку), решение attributable.
- **LAW 5** — `LlmOptimizer` не предлагает изменений при `confidence < 0.7`.
- **LAW 6** — `IOptimizer` теперь имеет 2 реализации (PatternBased + Llm),
  что оправдывает порт ещё сильнее.
- **LAW 8** — новый Wave → новый ADR (этот).

## Открытые вопросы (резолв архитектором)
1. **LlmOptimizer — адаптер, НЕ новый порт.** ✅ Согласен с пользователем.
   Реализует `IOptimizer.recommend(patterns, current_config)`, расширять сигнатуру
   не нужно — `current_config` уже несёт контекст.
2. **DocMaintainer — READ-ONLY.** ✅ Согласен. Генерирует `proposed_diffs`,
   не пишет файлы. Auto-commit в Obsidian — вне Wave 14.
3. **Интеграция в AgentPlatform.** Добавить
   `autonomy_controller: Optional[IAutonomyController] = None` в `__init__` и
   вызывать `_retrospect()` в конце `run()` (после `_recommend()`). НО:
   `_retrospect()` требует `learning_store` (откуда брать `traces`). Если
   `autonomy_controller` задан, а `learning_store` — нет, retrospective
   пропускается (warn, не падает). Добавляется поле `autonomy_log` в `AgentResult`
   (frozen, observe-only, как `optimization_recommendations`).
4. **Техдолг — отдельный поток «Debt Triage».** ✅ Согласен. Wave 14 закрываем с
   ЧИСТЫМ арх-гейтом (0 новых нарушений). `workflow_runner.py` cross-import,
   `graph_query_engine.py`, осиротевшие `stubs/`, `test_graph_*` — НЕ в моих
   коммитах Wave 14.

## Корректировки по фактическому коду (честный фикс расхождений)
- **A.** Черновик считал `plan_success_rate` по `StepStatus.DONE` шагов. В коде
  `StepTrace` НЕ имеет `status` (поля: step_id, model_id, prompt, output,
  tools_used, cost, latency_ms, eval_score). Источник — `ExecutionTrace.final_status
  == "done"`. Метрика пересчитана на per-trace basis.
- **B.** `pattern_drift` — черновик предполагал history. В коде `ConfigApplier.
  history()` НЕ несёт статуса рекомендации (только previous/new/approved_by/
  rec_id/target/timestamp). Drift считается по `applier.status(rec_id)` ∈
  {approved, applied, rolled_back}. (Опц. расширение `_ChangeRecord.kind` — решаем
  в Phase B.)
- **C.** Интеграция требует `learning_store` для retrospective (см. п.3 выше).
- **D.** `EvaluationReport.attention` — `Tuple[str, ...]` (id рекомендаций),
  семантика: «требуют human-внимания» (например, drift > порога).

## Границы (scope lock)
Не входит: автоматический git commit / push; изменение ядра волн 5–13; решение
pre-existing техдолга; LLM для применения конфигурации (LLM только для
генерации `Recommendation.value`, и только при `confidence > 0.7`).

## Риски
- **Prompt injection в LlmOptimizer** — `value` может содержать вредоносный JSON.
  Guardrail: whitelist путей + schema validation перед `propose()`.
- **Loop autonomy** — бесконечная ретроспектива. Guardrail: rate-limit в
  `ThresholdAutonomyController` (max 1/час).
- **Doc drift vs code** — DocMaintainer может предложить неверный diff. Guardrail:
  dry-run по умолчанию, apply только после human review.

## Definition of Done (Wave 14)
- [ ] Порты `IAutonomyController`, `ISelfEvaluator`, `IDocMaintainer` + entities в `contracts/i_autonomy.py`
- [ ] `ThresholdAutonomyController`, `SimpleSelfEvaluator`, `StaticDocMaintainer` (v0.1) в `services/`
- [ ] `LlmOptimizer` (адаптер `IOptimizer`) в `services/`
- [ ] Интеграция в `AgentPlatform.run()`: опциональный `autonomy_controller` + `_retrospect()` + поле `autonomy_log`
- [ ] Тесты: contract/adapter/integration/live-gated (6+ файлов)
- [ ] Регресс волн 5–13: зелёный
- [ ] ADR-017 → accepted, Roadmap → Wave 14 ✅, Build Journal → Wave 14, MOC обновлён
