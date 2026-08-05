---
id: ADR-087
title: Runnable launch + persistence + optional local LLM (ТЗ-LIVE-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-054   # Cognitive Kernel FSM / self-evolution
  - ADR-074   # SKILL-01 procedural consolidation
  - ADR-085   # CAPSTONE (live run baseline)
  - ADR-086   # NET-ROUTE-01 (multi-hop)
decision: >-
  Ядро deterministic + self-evolving, но опыт in-memory терялся между перезапусками.
  ТЗ-LIVE-01 замывает этот разрыв: (1) JsonMemoryStore (stdlib json) персистит
  SOFT-слой эволюции (episodes/semantic/normative + skills + trust) в JSON-файл;
  (2) run_evolution.py строит ядро (+ опц. Ollama-advisor), грузит/реплеит состояние,
  гоняет поток целей, печатает эволюцию (policies/skills/trust), сохраняет состояние;
  (3) опц. локальный LLM (detect_local_ollama -> build_llm_client) подключается как
  ILLMAdvisor, skip-if-unavailable (ядро LLM-free по конструкции).
evidence_level: V
addresses:
  - TZ-LIVE-01
---

## Context
Когнитивное ядро (ADR-054) детерминировано и self-evolving (soft-политики из повторяющихся
исходов через ReferenceExecutor; процедурные навыки через ProcedureConsolidator). Но состояние
жило in-memory и сбрасывалось при перезапуске — "наблюдать эволюцию" было невозможно между
запусками. ТЗ-LIVE-01 делает запуск реальным: ядро эволюционирует между перезапусками.

## Decision
- **Persistence (kernel/persistence.py):** `JsonMemoryStore` + `KernelState` (frozen dataclass).
  Сохраняет 4 среза — `episodes`, `semantic`, `normative` (из layered memory, включая soft-политики
  = эволюция), `skills` (Procedure VOs), `trust` (dict). Сериализация явная (VO<->dict), НЕ
  `dataclasses.asdict`, т.к. ConfidenceScore/Provenance/CausalMark несут вложенные enum + Lamport-clock.
  `json.dump(sort_keys=True)` -> детерминированный roundtrip (I-09). K1: stdlib json only.
- **Inject-store (KernelConfig.memory):** опц. `memory` в KernelConfig + ветка в KernelBuilder ->
  ядро строится поверх загруженного стора и RESUME самоэволюцию. Backward-compat (None -> fresh).
  `procedural` НЕ добавлен в kernel (kernel не держит процедурный стор; K3/K6: kernel не импортирует
  services). Навыки/trust персистятся на уровне run_evolution.py (composition root).
- **Entry point (run_evolution.py, Флаг C):** root-скрипт, кросс-слойная сборка (kernel + services +
  composition) — как в tests/. load -> replay в память -> build_kernel(memory=...) -> N тиков
  демо-потока -> печать эволюции -> save. Опц. Ollama через `detect_local_ollama`/`build_llm_client`,
  обёрнут в try/except -> skip-if-unavailable (никогда не ломает запуск).

## Constraints honored
- **K1/K6:** stdlib json; kernel/persistence.py импортирует только kernel + contracts + stdlib;
  kernel НЕ импортирует services (чистота слоёв).
- **O1:** persistence НЕ мутирует HARD — load восстанавливает сохранённое как есть; kernel только
  коммитит SOFT через memory_evolution, HARD immutable (deprecate_normative('hard') raises).
- **I-09:** load детерминирован (тот же файл -> то же состояние); без LLM запуск детерминирован
  (эволюция идентична; opaque random episode-id исключён из гарантии).
- **Флаг C:** run_evolution.py standalone. **Флаг 1b:** тесты отдельным коммитом.

## Positive
- Ядро впервые реально "развивается между перезапусками" — замкнут цикл observe→learn→persist→resume.
- K5: переиспользованы все порты/строители; создан ровно один новый модуль (persistence.py).
- Запуск без Ollama работает (deterministic baseline); Ollama — чистый опциональный адвизор.

## Negative / non-scope
- Реальный multi-host TCP, PKI/Ed25519, консенсус — post-MVP (ADR-086).
- Богатый CLI/daemon — только простой entry point.
- seen-set (NET-ROUTE-01) и ring-routing — упрощения (light flags ТЗ-NET-ROUTE-01).
- HARD-политики НЕ эволюционируют (O1 намеренно).

## Alternatives considered
- `dataclasses.asdict` для сериализации — отвергнут: не раскрывает enum/Lamport-clock корректно,
  ломает roundtrip вложенных VO.
- Внедрить procedural-стор в kernel — отвергнут: kernel не владеет навыками (K3/K6), навыки живут
  в orchestrator/run_evolution.
- SQLite вместо JSON — отвергнут: K1 (stdlib-only) + простота roundtrip; JSON достаточен для MVP.

## Testing
- `tests/test_live_persistence.py` (K8): roundtrip идентичен; эволюция через 2 перезапуска
  (6->10 эпизодов, soft-политика переживает restart); O1 HARD intact + immutable; детерминизм
  без LLM; запуск без Ollama. Gate 14 + akb-lint + full suite 0 failed.
