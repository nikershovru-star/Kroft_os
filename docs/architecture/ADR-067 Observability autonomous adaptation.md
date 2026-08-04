---
id: ADR-067
title: "Observability — live metrics feed autonomous runtime adaptation (ТЗ-OBS-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.88
confidence: high
risk: low
related: [ADR-040, ADR-062, ADR-044, ADR-054, ADR-065, TZ-015, RT-01, NW-01, SE-01, I-08, I-10]
addresses: [TЗ-OBS-01, O1, K1, K6, K8, RT-01-DEBT]
---

## 1. Context
RT-01 (runtime reflection) тюнингует SOFT-параметры, но метрики подаются injectable
`ReferenceRuntimeMetrics.set_snapshot(...)` — задокументированный долг: адаптация не
автономна, сигналы подаются ИЗВНЕ. OBS-01 делает метрики ЖИВЫМИ: инструментирует
ядро/федерацию/execution/память счётчиками и кормит ими `RuntimeSupervisor`, чтобы тот
адаптировался АВТОНОМНО. Закрывает долг RT-01; даёт телеметрию для инспекции всей
построенной сложности (федерация, эволюция, LLM-advisor).

## 2. Decision — observability boundary
- **Порт `ILiveMetricsCollector`** (contracts/i_observability.py) — ОТДЕЛЬНАЯ граница от
  `contracts/i_metrics.py: IMetricsCollector` (системные метрики psutil). KROFT
  one-port-per-boundary: НЕ дублируем имя/границу (K5 baseline: `IMetricsCollector`
  уже занят системным портом — переименование в `ILiveMetricsCollector`).
- **Метрики = ОТНОШЕНИЯ, не сырые инкременты (Флаг 1).** Collector хранит
  числитель+знаменатель и вычисляет ratio на `collect`: `execution.success_rate =
  success/total`, `federation.delivery_success_rate = delivered/(delivered+dropped)`,
  `llm.fallback_rate = fallbacks/advisor_calls`, `memory.growth_rate_per_tick =
  episodes/ticks` (скользящее окно). Без этого R1/R3 (сравнивают с долями) не
  сработают.
- **`memory.consolidation_confidence` определена при разреженной консолидации (Флаг 2):**
  считается по скользящему окну исходов (avg utility за окно), при пустом окне —
  carry-last, нет истории — нейтральный 0.5 (НЕ «нет значения»). Иначе сценарий R3
  (degraded, ничего не консолидируется) не триггернул бы в нужный момент.
- **`LiveRuntimeMetrics(IRuntimeMetrics)`** (kernel/observability.py) читает ЖИВЫЕ
  счётчики + текущие tunable-значения (из `memory_evolution`/`network_transport`) и
  эмитит `List[RuntimeMetric]` — зеркально `build_runtime_metrics`. `ReferenceRuntimeMetrics`
  (injectable) СОХРАНЯЕТСЯ для RT-01 тестов (не ломаем).
- **Автономный цикл + гистерезис (Флаг 3):** `RuntimeSupervisor.step()` крутится раз в
  N tick (не каждый — иначе thrashing), proposal применяется при устойчивом пересечении
  порога. Negative-тест («здоровые → порог не ползёт») честен.

## 3. Architecture
```
[Kernel hooks] -> collector.record_*(execution/federation/memory/llm)
                        |
                        v
              LiveMetricsCollector (ratios, sliding window)
                        |
                        v  LiveRuntimeMetrics.collect()  [живые счётчики + tunable.current]
                        |
                        v
              RuntimeSupervisor.step() -> reflect(R1/R2/R3) -> applier.apply (O1: только SOFT)
                        |
                        v  (раз в N tick, гистерезис)
              memory_evolution._thr / _min_rep  [тюнинг SOFT-параметров]
```
Hook-точки no-op при выключенном collector (поведение ядра не меняется).

## 4. Capstone proof (tests/test_observability_adaptation.py, K8)
- **CAPSTONE**: degraded исходы (executor fail / low reward) -> живая
  `memory.consolidation_confidence` падает (< 0.6) -> supervisor АВТОНОМНО поднимает
  `memory.confidence_threshold.current` (R3) -> измеримо МЕНЬШЕ консолидаций. Без
  injectable snapshot — из живых метрик.
- **NEGATIVE**: здоровые исходы -> порог не ползёт (гистерезис/разрежённый цикл).
- **O1**: только SOFT тюнитуется (enforced в `ITuningApplier.apply`); HARD/FSM/контракты
  неизменны; no-op при выключенном collector.
- Существующие RT-01 тесты НЕ сломаны (`ReferenceRuntimeMetrics` сохранён).

## 5. Relationship to O1 / K1 / K6 / K8 / I-08 / I-10
- **O1**: supervisor тюнитует только SOFT (timeout/threshold/budget); FSM/HARD/контракты
  untouched (enforced в applier).
- **K1**: contracts/i_observability.py stdlib+contracts; kernel/observability.py K1 (только
  contracts).
- **K6**: collector зависит от порта ILiveMetricsCollector; ядро импортирует только порт.
- **K8**: negative (здоровые → не ползёт) + O1 обязательно тестируются.
- **I-08/I-10**: телеметрия для инспекции federated/evolved/advisor-сложности; LLM-free
  core сохранён.

## 6. Constraints / Non-scope (per ТЗ)
- Полноценный tracing/profiling UI; экспорт во внешние APM; реальные LLM-адаптеры;
  RL/bayesian optimization (reference rules только) — НЕ в scope.
- Переиспользовать ITelemetrySink (TZ-015) для времянки; НЕ дублировать порт.

## 7. Test Stability (honest note)
Капстоун детерминирован: degraded исходы подаются через ReferenceExecutor (как SE-01);
supervisor крутится раз в N tick с гистерезисом. `--count=5` не требуется (детерминирован
по RT-01 принципу монотонных bounded-правил).

## 8. Future Work
- Репутация/decay федерированных норм (Флаг 2 FSE-01) — связать с
  `federation.delivery_success_rate`.
- Weighted federation + эмиссия в реальный ITelemetrySink для долгосрочной телеметрии.
