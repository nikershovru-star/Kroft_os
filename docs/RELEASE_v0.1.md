# KROFT_OS v0.1 — Release

**Autonomous Intelligence Operating System** — самоэволюционирующееся ядро с памятью,
marketplace'ом навыков, федерацией узлов и observability-панелью управления.

```
✔ ядро (Cognitive Kernel, FSM, детерминизм)
✔ память (layered + procedural + knowledge graph)
✔ marketplace (skill packaging / distribution / trust)
✔ federation (cross-node skill replication)
✔ desktop dashboard (KROFT Desktop — system-at-a-glance)
```

Это уже **продукт**, которым можно пользоваться — не инженерный эксперимент.

## Быстрый старт

```bash
# поднять весь стек + live-демо (без LLM, детерминированно)
python composition/run_kroft.py

# с mock-LLM советником
python composition/run_kroft.py --llm mock

# включить федерацию (SkillDistributor loopback)
python composition/run_kroft.py --federation

# только boot, без демо-цикла
python composition/run_kroft.py --no-demo
```

Подробнее: [docs/RUN.md](RUN.md).

## Что показывает панель KROFT Desktop

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

Цифры — **реальное состояние подсистем** (agents из IdentityRegistry, models из ModelRegistry,
skills из SkillRepository, notes из Knowledge Graph, trust из TrustRegistry). Tasks = 0 пока
TaskStore не подключён (post-MVP daily-use pipeline).

## Архитектура (capability stages, closed)

1. **LIVE** — boot ядра
2. **OmniRouter** — маршрутизация моделей (free-online + local)
3. **Agent Loop** — FSM kernel tick
4. **Knowledge Engine** — layered + procedural memory
5. **Evolution** — LLM-free SkillEvolver (v1→v2)
6. **Marketplace** — skill packaging / distribution / trust
7. **Federation Replication** — cross-node skill sync
8. **Observability Dashboard** (Этап 8) — KROFT Desktop

**Capstones:** cross-node knowledge exchange (FED-01) + distributed self-evolution (CAPSTONE-02).
**Security core:** per-author HMAC-keys (AUTHOR-KEYS-01) + distribution/rotation/revocation (KEYDIST-01).

## Экосистема (дорожная карта)

```
KROFT_OS
├── Desktop      ✔ KROFT Desktop panel (run_kroft)
├── CLI          ✔ python composition/run_kroft.py
├── API          — post-MVP
├── SDK          — post-MVP
├── Marketplace  ✔ skill packaging/distribution
├── Federation   ✔ SkillDistributor (loopback)
├── Plugins      — post-MVP
├── Templates    — post-MVP
├── Documentation ✔ docs/
└── Community    — post-MVP
```

## Что НЕ входит в v0.1 (post-MVP, после реальной эксплуатации)

- **Enterprise Security:** Ed25519 / PKI / Certificate Authority, key rotation,
  distributed bootstrap, trusted federations — после появления реальных пользователей.
- **GUI:** полноценный pyautogui/оконный интерфейс (сейчас — консольная панель).
- **Real multi-host TCP federation:** сейчас loopback-транспорт.
- **Daily-use pipeline:** Obsidian → Knowledge Engine → Hermes → Agent Loop → Marketplace.
- **Собственные AI-агенты:** Sales / Research / Architect / Programmer / Writer / Finance.

## Принципы

- **K1** — stdlib + contracts only в домене (без 3rd-party SDK).
- **K5** — reuse существующих компонентов, один шов на границу.
- **K6** — services импортируют только contracts.
- **O1** — default-deny (не trusted/tampered → reject).
- **I-09** — детерминизм (LLM-free эволюция, HMAC-детерминизм).

## Тесты

```bash
pytest -q            # полный прогон (0 failed)
pytest tests/desktop # dashboard + run_kroft
```

Arch-gate (K1/K3/K6/K8 + F1–F6): 14 positive + 6 negative. akb-lint: 100 ADR PASSED.

## v0.1.1 — Daily-use (ТЗ-DAILY-01)

Панель больше НЕ demo-seed. Живые данные:

- `Memory` = реальное число заметок vault (`--vault <path>` → ObsidianVaultReader → KnowledgeEngine → граф).
  Реальный Obsidian Vault → ~16000+ notes (живые). Без `--vault` → 0 (graceful).
- `Tasks` = реальные задачи из `TaskStore` (интерактивный контур создаёт задачу на каждый query).
- Интерактивный контур `--interactive`: query → kernel FSM tick → `ReferenceSearchService` отвечает
  из живого графа (поиск по реальным заметкам vault).

```bash
PYTHONPATH=. python composition/run_kroft.py --vault "C:\Users\Nikita\Documents\Obsidian Vault" --interactive
```
