# KROFT_OS v0.1 — Руководство запуска (RUN.md)

Одна команда поднимает весь стек KROFT_OS (kernel + опц. LLM + эволюция + опц. федерация +
dashboard) и запускает live-демо цикл.

## Требования

- Python 3.11+
- Репозиторий KROFT_OS (stdlib-only домен, без внешних SDK в рантайме)
- Для `--llm auto` — доступный LLM-endpoint (опционально; по умолчанию `none` = LLM-free)

## Запуск

```bash
# из корня репозитория
PYTHONPATH=. python composition/run_kroft.py [OPTIONS]
```

### Опции

| Опция | Значение | Описание |
|---|---|---|
| `--node-id` | `nodeA` | идентификатор узла |
| `--llm` | `none` \| `mock` \| `auto` | LLM-советник: нет / детерминированный mock / реальный клиент |
| `--federation` | flag | включить SkillDistributor (loopback-транспорт) |
| `--ticks` | `5` | число итераций демо-цикла |
| `--no-demo` | flag | только boot, без демо-цикла |

### Примеры

```bash
# 1) Минимальный детерминированный прогон (без сети/модели)
PYTHONPATH=. python composition/run_kroft.py --llm none --ticks 5

# 2) С mock-LLM (детерминированный, без сети)
PYTHONPATH=. python composition/run_kroft.py --llm mock --ticks 3

# 3) С федерацией (loopback)
PYTHONPATH=. python composition/run_kroft.py --federation --ticks 2

# 4) Только boot (сервисы готовы, демо не запускается)
PYTHONPATH=. python composition/run_kroft.py --no-demo
```

## Панель KROFT Desktop

После boot'а `run_kroft` печатает панель на каждом tick:

```
KROFT Desktop
──────────────────────────
Kernel
  ✓ Running
Agents
  6 active
Tasks
  0 queued
Models
  llama3
  qwen3.5
Marketplace
  52 skills
Federation
  0 nodes
Memory
  245 notes
Trust
  0.97
Logs
  ...
──────────────────────────
```

### Интерпретация цифр

| Поле | Источник | Примечание |
|---|---|---|
| **Kernel** | `kernel._state.name` | `✓ Running` при любом состоянии кроме STOPPED/FAILED |
| **Agents** | `IdentityRegistry.list()` | demo-seed: 6 агентов (Research/Architect/Programmer/Writer/Finance/Sales) |
| **Tasks** | `TaskStore` | **0** — TaskStore ещё не подключён (post-MVP daily-use) |
| **Models** | `ModelRegistry.catalog()` | demo-seed: qwen3.5, llama3 |
| **Marketplace** | `SkillRepository._installed` | demo-seed: 52 навыка |
| **Federation** | `SkillDistributor._peers` | 0 без `--federation`; >0 при включённой федерации |
| **Memory** | `InMemoryGraphEngine.nodes()` | demo-seed: 245 notes (knowledge graph) |
| **Trust** | `ReferenceTrustRegistry.current_trust` | агрегат (mean) по зарегистрированным авторам; demo 0.97 |
| **Logs** | ring buffer | последние 5 строк (tick-логи) |

**ВАЖНО:** в v0.1 demo-компоненты (6 agents / 52 skills / 245 notes) — это composition-level
scaffolding для демонстрации панели. В реальной эксплуатации (daily-use pipeline) они заменяются
живыми данными из ваших Obsidian-заметок, реальных агентов и установленных навыков.

## Read-only

Dashboard — **read-only** (O1). Он читает состояние подсистем через публичные аксессоры и
ничего не мутирует. Snapshot детерминирован (I-09), JSON-рендер stable (`sort_keys`).

## Тестирование

```bash
PYTHONPATH=. python -m pytest tests/desktop/test_dashboard.py tests/desktop/test_run_kroft.py -q
# 16 passed (dashboard 8 + run_kroft 8)

PYTHONPATH=. python -m pytest -q   # полный прогон, 0 failed
```

Arch-gate: `pytest tests/ -k "architecture"` (14 positive + 6 negative). akb-lint: 99 ADR PASSED.

## Следующие шаги (post-MVP)

1. Ежедневно использовать систему для своей работы (архитектура, Obsidian, разработка).
2. Собирать реальные проблемы эксплуатации (не придумывать новые абстракции).
3. Подключить TaskStore + реальный Obsidian→Knowledge Engine→Agent Loop pipeline.
4. Создать собственных агентов (Sales/Research/Architect/Programmer/Writer/Finance).
5. После недель реального использования — v0.2 (Ed25519/PKI, полноценная федерация).
