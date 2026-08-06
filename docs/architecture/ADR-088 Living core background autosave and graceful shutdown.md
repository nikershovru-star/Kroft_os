---
id: ADR-088
title: Living core — background autosave, SIGINT graceful shutdown, live mode (ТЗ-LIVE-01 extended)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-087   # Runnable launch + persistence + optional local LLM (ТЗ-LIVE-01 base)
  - ADR-054   # Cognitive Kernel FSM / self-evolution
  - ADR-074   # SKILL-01 procedural consolidation
  - ADR-085   # CAPSTONE (live run baseline)
decision: >-
  ТЗ-LIVE-01 (ADR-087) дал persistence + launch, но ядро всё ещё "стартовало и сразу
  останавливалось" после N тиков. Расширение превращает его в ЖИВУЮ систему (Этап 1 roadmap):
  (1) run_evolution.py принимает --state-dir (директория, default ./kroft_state) вместо
  отдельного файла; состояние = <dir>/kernel_state.json; директория создаётся при старте;
  (2) --llm {auto,none} заменяет --no-llm: auto = detect_local_ollama -> build_llm_client
  (Ollama localhost:11434/v1), иначе LLM-free детерминированный run; none = форс LLM-free;
  (3) --ticks 0 = LIVE/forever mode (блокирует до SIGINT), N = run N тиков затем exit+save;
  (4) фоновый autosave-таймер (stdlib threading.Timer, --autosave-sec default 30; 0 выкл)
  периодически сохраняет состояние, защищая эволюцию при долгой работе;
  (5) опц. фоновый consolidation-тик (--bg-consolidate, ВЫКЛ по умолчанию, детерминирован);
  (6) graceful SIGINT: signal handler сохраняет состояние + останавливает таймер + exit 0.
evidence_level: V
addresses:
  - TZ-LIVE-01
---

## Context
ADR-087 замкнул цикл observe->learn->persist->resume для одного прогона. Но "живое ядро,
которое можно запустить и не выключать" требовало: (a) безопасного периодического
сохранения при долгой работе (autosave), (b) корректной остановки по Ctrl-C без потери
опыта (SIGINT), (c) режима "live" (блок до сигнала), (d) удобной точки монтирования
состояния (state-dir). ТЗ-LIVE-01 extended закрывает эти пробелы.

## Decision
run_evolution.py (Флаг C, composition-root) расширен:
- **state-dir**: `--state-dir D` -> `D/kernel_state.json`; `os.makedirs(D, exist_ok=True)`.
- **llm auto/none**: `auto` (default) зондирует Ollama через `detect_local_ollama()` и при
  успехе строит `build_llm_client()` (skip-if-unavailable: отсутствие Ollama НЕ ошибка,
  ядро LLM-free по конструкции). `none` форсит детерминированный LLM-free run.
- **live mode**: `--ticks 0` блокирует в цикле (sleep 0.2) до SIGINT, прогоняя детерминированный
  demo-поток; N>0 гоняет N тиков и завершается с final save.
- **autosave timer**: `_LivingCore._schedule_autosave` ставит `threading.Timer(autosave_sec,
  _autosave_loop)` (daemon); loop сохраняет и перепланирует; `stop_autosave()` отменяет.
- **SIGINT**: `signal.signal(SIGINT, handler)` -> `stop_autosave(); save(); sys.exit(0)`.
- **bg consolidate**: `--bg-consolidate` (off by default) — задел для фонового consolidation/
  reflection тика; в текущей реализации детерминирован и выключен, чтобы не менять поведение.

## Constraints honored
- K1/K6: run_evolution.py — composition-root (импортирует kernel+services+composition);
  фон-сервисы на stdlib (threading/signal), НЕ тянут V3 runtime/kernel_runtime.py.
- K5: переиспользованы JsonMemoryStore, build_kernel, detect_local_ollama/build_llm_client,
  ProcedureConsolidator, ReferenceExecutor, ReferenceTrustRegistry, InMemoryProceduralMemory.
  НОВЫХ портов/классов НЕ создано (только расширение entry-point).
- I-09: без LLM run детерминирован; load детерминирован (sort_keys json).
- O1: autosave/load НЕ мутируют HARD (ядро коммитит только SOFT-слой).
- Флаг 1b: тесты отдельно (tests/kernel/test_live_core.py).

## Consequences
- Ядро можно запустить `python run_evolution.py --state-dir ./kroft_state` и оставить работать;
  autosave защищает эволюцию; SIGINT останавливает корректно.
- Состояние накапливается между перезапусками (resume через JsonMemoryStore load+replay).
- Non-scope (post-MVP): daemon/systemd, GUI/Desktop (Этап 8), реальный multi-host.
