---
tags: [kroft-os, l10, l10.6, persistence-recovery, state-isolation, read-only-audit]
created: 2026-08-10
status: READ-ONLY VERIFY — no code change
verdict: PASS WITH GAPS
production-mutation: NONE
---

# L10.6 — Persistence Recovery & State Isolation — READ-ONLY VERIFY

**Режим:** VERIFY ONLY. Никаких изменений production-кода, commit, push, re-embed, reindex.

## КРИТИЧЕСКОЕ РАСХОЖДЕНИЕ ТЗ С ФАКТИЧЕСКИМ CODEBASE

ТЗ L10.6 описывает persistence-модель:
`PersistentMemoryService` → `runtime.ingest_learning()` → `runtime.save_state()` → `runtime_memory.json`,
с лимитами `max_turns=200 / max_facts=1000 / max_episodes=500 / max_procedures=500`.

**Этой модели НЕТ в активном production-коде KROFT_OS.** Поиск по repo:
- `class PersistentMemoryService` → 0 совпадений (только `archive/KnowledgeOS-v5/...` — старый архив).
- `build_default_runtime` / `KROFTOSRuntime` → 0 совпадений.
- `runtime_memory.json` → 0 файлов в активном дереве.
- `max_turns=200 / max_facts=1000 / max_episodes=500 / max_procedures=500` → 0 (в `archive/KnowledgeOS-v5/services/session_store.py` `max_turns=2`; в активном `services/session_store.py` `max_turns=50`).

**Фактический production persistence path (что реально существует):**
1. `InMemoryLayeredMemory` (`kernel/memory_store.py`) — episodes / semantic / normative (in-memory, сохраняется через KnowledgeSnapshotStore).
2. `KnowledgeSnapshotStore` (`composition/knowledge_persistence.py`) — пишет `_runtime_snapshot.json` (PHASE A containment: runtime state отдельно от foundation `_snapshot.json`).
3. `KroftApp._save_knowledge` / `_restore_episodic/_restore_semantic/_restore_normative` (`composition/run_kroft.py:605-699`) — production runtime path (вызывается из `__init__` и после каждого query).
4. `SessionStore` (`services/session_store.py`) — turns/last_find, JSON-файл, `max_turns=50`.
5. `IncrementalTracker` (`services/incremental_tracker.py`) — vault-crawl state (НЕ facts/episodes autonomous-loop).

Аудит проведён по ФАКТИЧЕСКОЙ архитектуре (ТЗ STEP 1 требует "production runtime path, а не тестовый объект" — он и проверен).

## STEP 1 — Persistence wiring (фактический production path)

| Переход | Файл | Класс/функция | Вызов | PASS/FAIL |
|---|---|---|---|---|
| entry | `composition/run_kroft.py` | `KroftApp.__init__` | `_save_knowledge()` (402), `_restore_episodic` (397) | PASS (production path) |
| save | `composition/run_kroft.py:655` | `_save_knowledge` | `self._runtime_store.save(episodes=..., semantic=..., normative=..., procedural=..., trust=...)` | PASS |
| store | `composition/knowledge_persistence.py:38` | `KnowledgeSnapshotStore.save` | `json.dump(payload, open(path,"w"))` | PASS (works) / **FAIL atomicity** (см. STEP 5) |
| restore | `composition/run_kroft.py:605` | `_restore_episodic` | `_runtime_store.load_episodic()` → `_episode_from_dict` → `self.memory._episodes = restored` | PASS |
| loop use | `kernel/agent_loop.py` | `AgentLoop.run` | `build_kernel(memory=self._memory)` → `kernel.tick` → `record_episode` | PASS |

Это РЕАЛЬНЫЙ production runtime path (не тестовый double).

## STEP 2 — Persistence domains (фактические)

| Domain | Write | Persist | Restore | Runtime use | Status |
|---|---|---|---|---|---|
| turns | `SessionStore.add_turn` | JSON file | `SessionStore.load` | agent_service implicit commands | PASS (separate subsystem) |
| facts (semantic) | `InMemoryLayeredMemory.commit_semantic` | `_runtime_snapshot.json` (`semantic`) | `_restore_semantic` | reasoning (КROFT Self-Model) | PASS |
| episodes | `InMemoryLayeredMemory.record_episode` | `_runtime_snapshot.json` (`episodes`) | `_restore_episodic` | **L10.5 past-experience retrieval** | PASS |
| procedures | `ProceduralMemory` (run_kroft) | `_runtime_snapshot.json` (`procedural`) | `_save_knowledge` writes `procedural=` | SkillEvolver | PASS |
| metadata | `KnowledgeSnapshotStore.save(meta=...)` | `_runtime_snapshot.json` (`meta`) | loaded back | diagnostics | PASS |

## STEP 3 — Restart / recovery trace

`KroftApp A` → tick → `record_episode` → `LayeredMemory._episodes` → `_save_knowledge` → `_runtime_store.save` (`_runtime_snapshot.json`).
Terminate → `KroftApp B` (same `knowledge_snapshot` path) → `__init__` → `_restore_episodic` → `self.memory._episodes = restored`.
**Runtime B ПОЛУЧАЕТ состояние Runtime A** (доказано в L10.4: Treatment restored 5 episodes, Control 0).
Проверка не создавала новых production данных (использовала изолированный TMP в L10.4).

## STEP 4 — State isolation

`InMemoryLayeredMemory` — per-instance (`self._episodes = []` в `__init__`). Нет class-level mutable state, нет module globals, нет shared dict.
`KroftApp` создаёт свой `memory` (или получает injected). `record_episode` — чистый append.
**Новый runtime НЕ получает memory, которая не была загружена из persistence** — подтверждено (`_restore_episodic` загружает только из `_runtime_store`; без файла → `[]`).
ЕДИНСТВЕННЫЙ риск: `on_record_episode` hook (опц. callback) может быть shared между инстансами, если вызывающий назначит один и тот же callable — но это caller-responsibility, не дефолт.
Вердикт: **PASS** (isolation корректна по умолчанию).

## STEP 5 — Atomicity / corruption safety  ⚠️ GAP

`KnowledgeSnapshotStore.save` (`knowledge_persistence.py:98-99`):
```python
with open(self._path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ...)
```
- **НЕТ промежуточного `.tmp`**
- **НЕТ `os.replace()`**
- При краше во время записи → **частично записанный JSON** → файл повреждён.
- `load()` (106-111): при повреждённом JSON ловит Exception → `return None` (graceful degrade, теряет ВСЁ состояние).
- При отсутствии файла → `load` возвращает `None` (graceful).
- Recovery failure → молча теряет состояние (не поднимает ошибку, не бэкапит).

`SessionStore.save` (`session_store.py:91`): та же проблема (`open(path,"w")` без `.tmp`/`os.replace`).

**Это GAP:** ТЗ STEP 5 явно требует `.tmp → os.replace`. В production этого нет → риск corruption при unexpected termination. НЕ исправляется в L10.6 (только зафиксировано).

## STEP 6 — Capacity boundaries  ⚠️ GAP

- `InMemoryLayeredMemory.record_episode` (`memory_store.py:26-27`): `self._episodes.append(episode)` — **БЕЗ лимита**. Uncontrolled growth. `max_episodes=500` (ТЗ) **не реализован**.
- `KnowledgeSnapshotStore.save`: **без лимитов** на episodes/semantic/normative/procedural.
- `SessionStore`: `max_turns=50` (НЕ 200 из ТЗ); обрезает `turns[-max_turns:]`.
- `max_facts=1000 / max_procedures=500`: **не существуют**.
- metadata: `meta` dict сохраняется корректно (но без лимита размера).

**Вердикт:** capacity boundaries **FAIL** относительно ТЗ (лимиты из ТЗ отсутствуют; есть только `max_turns` в SessionStore=50).

## STEP 7 — L10.5 autonomous-loop continuity

`AgentLoop` → `record_episode` (via `kernel.tick`) → `LayeredMemory` (shared с run_kroft) → `_save_knowledge` → `_runtime_snapshot.json`.
New runtime → `_restore_episodic` → `memory._episodes` восстановлен.
Loop N+1 → `kernel.tick` → `_retrieve_similar_episodes` (semantic, L10.4) → `past-experience` fold → plan/result change.
**Доказано в L10.4 PASS:** restored memory реально меняет поведение loop. Autonomous-loop continuity = **PASS**.

## STEP 8 — Production integrity

- production SHA before == after: **3ea8fe3f6d318f82** ✅
- knowledge snapshot не изменён ✅
- vectors/indices/embeddings не изменены ✅
- unrelated working-tree changes (`run_kroft.py` 1136/882 uncommitted, etc.) НЕ затронуты ✅
- Никаких commit/push/re-embed/reindex ✅

## STEP 9 — Regression

Command:
`pytest tests/knowledge/test_cognitive_loop_persistence.py tests/agent_orchestration/test_agent_loop.py tests/knowledge/test_autonomous_learn_by_doing.py`
Result: **14 passed** (network-free, KROFT_EMBEDDING=none). No failures/skips.

## STEP 10 — FINAL VERDICT

```
L10.6 — Persistence Recovery & State Isolation
STATUS: PASS WITH GAPS

Persistence wiring:           PASS  (production runtime path real, not test double)
Memory domains:               PASS  (turns/facts/episodes/procedures/metadata all persist+restore)
Restart recovery:            PASS  (Runtime B gets Runtime A state; proven in L10.4)
State isolation:              PASS  (per-instance memory, no shared globals/leakage)
Atomic persistence:          FAIL  (GAP: no .tmp/os.replace → corruption risk)
Capacity boundaries:         FAIL  (GAP: no max_episodes/max_facts/max_procedures; max_turns=50≠200)
Autonomous-loop continuity:  PASS  (L10.5 restored memory changes new-process behavior)
Regression:                  PASS  (14 passed)
Production integrity:        PASS  (SHA 3ea8fe3f unchanged)

PATCH: NONE
```

### Задокументированные GAP (не исправляются в L10.6)

**GAP 1 — ТЗ-модель отсутствует в codebase (MAJOR)**
- Файл/модуль: отсутствует `PersistentMemoryService` / `runtime_memory.json` / `build_default_runtime` / `KROFTOSRuntime`.
- Проблема: ТЗ L10.6 целится в несуществующий persistence path. Фактический path = `InMemoryLayeredMemory` + `KnowledgeSnapshotStore`(`_runtime_snapshot.json`) + `SessionStore` + `IncrementalTracker`.
- Влияние на production: аудит по ТЗ-модели неприменим; нужна либо коррекция ТЗ под фактическую архитектуру, либо PATCH-TЗ на создание `PersistentMemoryService`.
- Минимальный следующий PATCH scope: уточнить ТЗ L10.x → аудит/патч фактического `KnowledgeSnapshotStore`+`SessionStore`.

**GAP 2 — Non-atomic persistence (corruption risk)**
- Файл: `composition/knowledge_persistence.py:98-99` и `services/session_store.py:91`.
- Функция: `KnowledgeSnapshotStore.save` / `SessionStore.save`.
- Проблема: прямая запись `open(path,"w")` без `.tmp`/`os.replace`. Краш → частичный JSON → `load` возвращает `None` → тотальная потеря состояния.
- Влияние: при unexpected termination runtime-state файл может быть уничтожен (graceful degrade = потеря ВСЕХ episodes/procedures/trust).
- Минимальный PATCH scope: в `save()` писать в `path + ".tmp"`, затем `os.replace(tmp, path)`; в `load()` при JSONDecodeError — не удалять, логировать + попытаться восстановить из `.bak`.

**GAP 3 — Нет capacity boundaries на layered memory**
- Файл: `kernel/memory_store.py:26` (`record_episode`), `:37` (`commit_semantic`), `:31` (`commit_normative`).
- Проблема: append без лимита. `max_episodes=500 / max_facts=1000 / max_procedures=500` (ТЗ) не реализованы. Только `SessionStore.max_turns=50`.
- Влияние: неограниченный рост `_episodes`/`_semantic` → memory leaks + slow retrieval (semantic retrieval эмбедит каждый episode при query).
- Минимальный PATCH scope: добавить `max_episodes`/`max_semantic`/`max_normative` в `InMemoryLayeredMemory.__init__` + обрезку FIFO при `record_*`; константы из ТЗ (500/1000/500).

---

**L10.6 = PASS WITH GAPS.** Recovery работает (Runtime B получает состояние A), isolation корректна, L10.5 continuity подтверждена, regression 14 passed, production интактен. Но ТЗ-модель persistence отсутствует в codebase, и выявлены 2 реальных production GAP-а (non-atomic save, отсутствие capacity limits), требующих отдельного PATCH-ТЗ. Никаких изменений не внесено.
