---
tags: [kroft, architecture-knowledge-base, akb, governance-as-code, adr-022, level-1-intelligence]
created: 2026-08-01
author: Hermes (Research Architect)
protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0 (Уровень 1 — Intelligence; enabler для Уровней 2/5 Review/Audit)
depends_on: [ADR-021 Runtime Evolution — Architecture Intelligence Synthesis, ADR-020 Runtime Host Architecture, ADR-002 Contracts, ADR-003 Event Bus, tests/test_architecture.py (arch-gate)]
summary: >-
  Architecture Knowledge Base (AKB) — machine-readable слой поверх существующего
  vault. Хранит LAW K1–K8 (как данные, не хардкод), индекс ADR-001..N, стандарты
  кодирования/интерфейсов, разрешённые/запрещённые паттерны, каталог технологий,
  историю изменений. Делает Уровни 2 (Review) и 5 (Code Auditor) автоматически
  проверяемыми. Исследованы: Backstage, OPA, Log4brains, Google AIP linter,
  Governance-as-Code. AKB = данные (YAML), читается Hermes и тестами; НЕ runtime-код
  (LAW K8 соблюдён). Код enforcement — отдельная фаза (Уровень 4), не здесь.
---

# ADR-022 — Architecture Knowledge Base (AKB)

> Protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0 — Уровень 1 (Intelligence)
> Enabler для Уровней 2 (Architecture Reviewer) и 5 (Code Auditor).
> Date: 2026-08-01. Scope: research + synthesis + AKB data skeleton. **No code in this ADR.**

---

## 1. Executive Summary

Пользователь верно диагностировал: исследование (Уровень 1) уже сильное (ADR-021),
но отсутствует **единая машиночитаемая архитектурная база знаний**. Без неё Уровни
2 (Review) и 5 (Audit) остаются *ручными* — Hermes не может при ревью запросить
«противоречит ли это ADR-020» или «нарушает ли LAW K8».

KROFT УЖЕ имеет зачаток AKB:
- `tests/test_architecture.py` (arch-gate) — хардкодит LAW K1–K8 как AST-проверку
  (в словаре `ALLOWED`). Это «seL4-lite» verifier.
- `docs/architecture/ADR-001..021` — markdown для людей, НЕ machine-readable.
- `Build Journal — Runtime Phase 1..6` — история, но prose, не данные.

**Проблема**: законы захардкожены в тесте; ADR нельзя запросить программно;
нет «запрещённых паттернов» как структуры; нет истории изменений как данных.

**Решение (ADR-022)**: AKB = **machine-readable YAML-слой поверх vault**, читаемый
Hermes (вне кода) и тестами (вне runtime). Законы, ADR, стандарты, паттерны,
техкаталог, история — всё как **данные**, не Python-модули. Enforcement (чтение
YAML в arch-gate) — отдельная фаза (Уровень 4), НЕ в этом ADR.

---

## 2. Existing Solutions (исследованы)

| Система | Что делает | Релевантность для KROFT |
|---|---|---|
| **Backstage** (Spotify) | Software Catalog + Tech Radar + TechDocs + automated checks. Единая база знаний индустрии. | Эталон. Но тяжёлый портал (Node/React) — избыточен для KROFT. Берём КОНЦЕПЦИЮ, не рантайм. |
| **OPA** (Open Policy Agent) | Policy-as-code (Rego), декуплирует правила от кода. | LAW K1–K8 как policy. НО Rego-движок — third-party → нарушит LAW K8 в runtime. Берём ИДЕЮ: политики = данные, проверка = Python (без движка) в tests/. |
| **Log4brains / adr-tools / MADR** | ADR как markdown в git рядом с кодом, метаданные из git logs. | KROFT уже markdown в vault. Добавить machine-readable ИНДЕКС (YAML) рядом. |
| **Google AIP + API linter** | «API linter automatically checks APIs for AIP violations, instant feedback». | Это Уровень 5 (Code Auditor). KROFT arch-gate = примитив. Расширить до AKB-driven linter. |
| **Governance-as-Code** | Правила version-controlled, enforced в SDLC. | Концептуальная обёртка: AKB = version-controlled governance. |

---

## 3. Engineering Research

- **Backstage**: catalog — YAML-описания сервисов (apiVersion, kind, spec). KROFT
  аналог: ADR/LAW/PATTERN как YAML-сущности с метаданными.
- **OPA**: «decouples policy from code; policies stored/tested/versioned in Git».
  → KROFT: `laws.yaml` version-controlled, проверяется тестом (не хардкод).
- **Google AIP linter**: линтер на каждом PR проверяет AIP. → KROFT: arch-gate
  читает `laws.yaml` + `patterns/forbidden.yaml`, fail на CI.
- **Log4brains**: `@adr` annotation для ссылок на код в ADR. → KROFT: ADR YAML
  содержит `ports_added`, `files_affected` для traceability.
- **Governance-as-Code**: «baked into code so enforced automatically throughout SDLC».
  → AKB lives в repo (docs/architecture/akb/), не в голове архитектора.

---

## 4. Cross-Domain Research

- **OS (seL4)**: formal verification = machine-checked proof. AKB = «seL4-lite»:
  законы как проверяемые утверждения (arch-gate), не informal doc.
- **Compliance (SOC2/ISO)**: control catalog как данные, audit проверяет соответствие.
  → AKB laws = control catalog; audit-тест = control verification.
- **Legal (GDPR)**: реестр обработки данных (RoPA) как структурированный документ.
  → AKB tech_catalog = реестр технологий с обоснованием.
- **ML (model card)**: карточка модели со школой, ограничениями, метриками.
  → AKB pattern = «карточка паттерна» (когда применять, риски, альтернативы).

---

## 5. Best Practices

1. **Knowledge as data, not prose** — YAML/JSON, читаемый программно.
2. **Version-controlled** — AKB в git/vault, history отслеживается.
3. **Enforced automatically** — arch-gate/tests читают AKB, fail на нарушении.
4. **Traceability** — ADR ссылается на LAW, LAW на ports, порты на файлы.
5. **Decouple policy from code** (OPA) — законы не хардкодятся в тесте.
6. **Single source of truth** — vault docs = SSOT, AKB = machine-readable projection.
7. **Incremental adoption** — AKB растёт с каждым ADR (Knowledge Base Update шаг).
8. **Backstage-style catalog** — сущности имеют kind/metadata/spec.

---

## 6. Common Anti-patterns

1. ❌ **Законы в коде теста** (текущий `ALLOWED` в arch-gate) — меняешь LAW →
   правишь тест. AKB: LAW в YAML, тест читает.
2. ❌ **ADR только для людей** — Hermes не может запросить. AKB: индекс YAML.
3. ❌ **Нет запрещённых паттернов** — «magic exactly-once», «sync backoff без yield»
   ловятся постфактум. AKB: `forbidden.yaml` + AST-grep в audit-тесте.
4. ❌ **Тяжёлый портал** (Backstage) для маленького проекта — over-engineering.
   AKB: лёгкие YAML + существующий arch-gate.
5. ❌ **Third-party policy engine в runtime** (OPA Rego) — нарушит LAW K8.
   AKB: данные + Python-проверка в tests/.
6. ❌ **История как prose** — нельзя запросить «что изменилось в LAW после ADR-015».
   AKB: `history.yaml` (commit → ADR → law-change).

---

## 7. Comparative Table

| Подход | Что взять | Что НЕ брать | Почему | Приоритет |
|---|---|---|---|---|
| Backstage | Catalog concept (kind/metadata/spec) | Node/React портал | Тяжело для KROFT | MED |
| OPA | Policy-as-data, decouple | Rego engine в runtime | Third-party нарушит LAW K8 | HIGH |
| Log4brains | ADR в git + индекс | Генератор сайта | Статичный сайт не нужен | HIGH |
| Google AIP linter | Automated AIP check на PR | Сам AIP процесс | KROFT свои LAW, не AIP | HIGH |
| Governance-as-Code | Version-controlled rules | — | Концепт | DONE |
| seL4 | Machine-checked proof | Formal verifier | Сверхсложно | LOW |

---

## 8. Risks

### 8.1 YAML как SSOT (дублирование с markdown ADR)
- **Риск**: ADR-021.md (prose) и adrs.yaml (data) расходятся.
- **Митигация**: yaml = индекс (id/title/status/ports), не дубликат содержимого.
  Hermes обновляет оба при ADR Draft.

### 8.2 Enforcement-код читает YAML (Уровень 4)
- **Риск**: тест падает из-за синтаксиса YAML, не из-за архитектуры.
- **Митигация**: strict schema validation; YAML парсится до проверок.

### 8.3 AKB разрастается (maintenance)
- **Риск**: 1 год — 50 LAW, 100 паттернов, никто не читает.
- **Митигация**: каждый LAW/PATTERN имеет owner-ADR; deprecated помечаются.

### 8.4 Ложные срабатывания audit-теста
- **Риск**: 6 мес — forbidden-pattern grep ловит false positive.
- **Митигация**: AST-проверка, не regex; whitelist легитимных случаев.

### 8.5 Нарушение LAW K8 (AKB в runtime)
- **Риск**: кто-то импортирует akb в `runtime/`.
- **Митигация**: AKB в `docs/architecture/akb/` (вне пакетов); arch-gate уже
  блокирует runtime→docs импорт.

---

## 9. Architecture Proposal (синтез)

**Принцип**: AKB = machine-readable projection vault docs. Данные, не код.
Читается Hermes (вне кода) и `tests/` (вне runtime). LAW K8 соблюдён.

### 9.1 Структура AKB (в `docs/architecture/akb/`)

```
akb/
├── laws.yaml              # LAW K1–K8 + будущие (id, text, scope, enforcement, severity)
├── adrs.yaml              # индекс ADR-001..N (id, title, status, supersedes, ports, laws)
├── standards/
│   ├── coding.yaml        # стандарты кодирования (naming, typing, no-circular)
│   └── interfaces.yaml    # стандарты интерфейсов (Protocol-only, runtime→contracts)
├── patterns/
│   ├── allowed.yaml       # разрешённые (supervision tree, reconcile, event-sourcing)
│   └── forbidden.yaml     # запрещённые (sync backoff, state в памяти, magic exactly-once)
├── tech_catalog.yaml      # каталог технологий (stdlib-only runtime; 3rd-party→infra/adapters)
└── history.yaml           # история: commit → ADR → law-change
```

### 9.2 Схема сущностей

```yaml
# laws.yaml
laws:
  - id: K1
    text: "Kernel импортирует только contracts.i_kernel, i_process, i_event_bus, runtime.*"
    scope: [kernel]
    enforcement: [ast]          # ast | manual | review
    severity: error             # error | warn
    owner_adr: ADR-020
  - id: K8
    text: "runtime/* импортирует ТОЛЬКО contracts.* + stdlib (+ локальные runtime)"
    scope: [runtime]
    enforcement: [ast]
    severity: error
    owner_adr: ADR-020

# adrs.yaml
adrs:
  - id: ADR-021
    title: "Runtime Evolution — Architecture Intelligence Synthesis"
    status: proposed
    supersedes: []
    relates_to: [ADR-020, ADR-019]
    ports_added: [ISupervisor, IReconciler]
    laws_affected: [K3, K8]
  - id: ADR-022
    title: "Architecture Knowledge Base"
    status: proposed
    ports_added: []
    laws_affected: [K8]

# patterns/forbidden.yaml
forbidden:
  - id: F1
    name: sync-backoff-without-yield
    rule: "runtime/supervisor/** не содержит time.sleep в recover-loop"
    detection: ast
    severity: error
    rationale: "Блокирует event loop; нарушает отказоустойчивость"
  - id: F2
    name: supervisor-state-in-memory
    rule: "RecoveryState НЕ хранится только в памяти supervisor"
    detection: review
    severity: warn
```

### 9.3 Enforcement (Уровни 2/5) — отдельная фаза (Уровень 4)

1. **Расширить `tests/test_architecture.py`**: читать `laws.yaml` (K1–K8) вместо
   хардкода `ALLOWED`. LAW становятся данными.
2. **Новый `tests/test_adr_compliance.py`**: проверяет, что новый код НЕ добавляет
   импорт/паттерн, запрещённый `adrs.yaml` (напр. runtime→services).
3. **Новый `tests/test_patterns.py`**: AST-grep `forbidden.yaml` (F1: time.sleep в
   supervisor; F2: помечает warn).
4. **Hermes (Уровень 2 Review)**: при ревью читает `adrs.yaml` + `laws.yaml`, ищет
   противоречия ДО написания кода.
5. **Knowledge Base Update (шаг цикла)**: после каждого ADR — обновить `adrs.yaml`
   + `history.yaml`.

---

## 10. ADR Draft (022)

**Title**: Architecture Knowledge Base (AKB) — machine-readable governance layer
**Status**: Proposed (research synthesis; enforcement — отдельная фаза Уровня 4)
**Decision**:
1. AKB = YAML-слой в `docs/architecture/akb/` (данные, не код).
2. LAW K1–K8 вынести из `tests/test_architecture.py` в `laws.yaml` (enforcement=ast).
3. ADR-001..N индексировать в `adrs.yaml` (id/title/status/ports/laws).
4. Паттерны (allowed/forbidden) — структурированные данные + AST-проверка.
5. Tech catalog + history — version-controlled.
6. Enforcement через расширение arch-gate (читает YAML) — НЕ в runtime (LAW K8).
**Consequences**:
- ✅ Уровни 2/5 становятся автоматически проверяемыми.
- ✅ LAW изменяются данными, не кодом теста.
- ✅ Traceability: ADR → LAW → ports → files.
- ⚠️ Maintenance: AKB растёт, нужен owner-ADR для каждой сущности.
- LAW K3/K8 соблюдены: AKB в docs/, не в runtime/; enforcement в tests/.

---

## 11. Recommended Interfaces (стабильные контракты AKB)

AKB — данные, интерфейсы = схемы YAML (не Python-типы):

```yaml
Law:        {id: str, text: str, scope: [pkg], enforcement: [ast|manual|review], severity: error|warn, owner_adr: str}
ADR:        {id: str, title: str, status: proposed|accepted|deprecated, supersedes: [str], relates_to: [str], ports_added: [str], laws_affected: [str]}
Pattern:    {id: str, name: str, rule: str, detection: ast|grep|review, severity: error|warn, rationale: str}
Tech:       {name: str, layer: runtime|infrastructure|adapters|services, allowed: bool, reason: str}
HistoryItem:{commit: str, adr: str, law_changes: [str], date: str}
```

**Стабильные**: схемы Law/ADR/Pattern (меняются редко, versioned).
**Расширяемые**: patterns/allowed (добавляются с каждым ADR).
**Заменяемые**: формат хранения (YAML→JSON), локация (docs→git).

---

## 12. Future Evolution

- **Рост**: AKB растёт с каждым ADR (Knowledge Base Update). 1 год — 30 LAW, 50 паттернов.
- **Стабильные**: схемы YAML (versioned, backward-compatible).
- **Расширяемое**: patterns/allowed, tech_catalog (по мере новых технологий).
- **Plugin-based**: новый LAW/PATTERN = новый YAML-блок, не код.
- **Phase 8 (multi-node)**: AKB распределяется как versioned config (consensus через
  `ICoordinator`, см. ADR-021); все узлы валидируют архитектуру единообразно.
- **Hermes integration**: Уровни 2/5 читают AKB перед ревью/аудитом; цикл замкнут.

---

## 13. Implementation Plan (фазы, не код в этом ADR)

| Фаза | Что | LAW | DoD |
|---|---|---|---|
| AKB-1 | Создать `akb/` YAML (laws, adrs-index, standards, patterns, tech_catalog, history) | K8 | файлы существуют, валидный YAML |
| AKB-2 | Расширить arch-gate: читать `laws.yaml` вместо `ALLOWED` | K8 | тест проходит, LAW из YAML |
| AKB-3 | `tests/test_adr_compliance.py`: imports не противорят `adrs.yaml` | K3 | новый импорт runtime→services → fail |
| AKB-4 | `tests/test_patterns.py`: AST-grep `forbidden.yaml` (F1 sync-backoff) | K8 | time.sleep в supervisor → fail |
| AKB-5 | Hermes Review (Уровень 2) читает AKB перед ревью | — | процесс документирован |
| AKB-6 | Knowledge Base Update: скрипт/чек-лист обновления при ADR | — | после ADR-023 adrs.yaml обновлён |

Каждая фаза — atomic commit (как Phases 1–6). AKB-1 (данные) можно сделать сразу
(не код). AKB-2..4 — Уровень 4 (реализация enforcement).

---

## 14. Testing Strategy

- **AKB-1**: YAML schema validation (pyyaml parse + required keys).
- **AKB-2**: arch-gate читает laws.yaml; совпадает с текущим `ALLOWED` (parity test).
- **AKB-3**: negative test — временный файл с runtime→services импортом → fail.
- **AKB-4**: negative test — supervisor с time.sleep → fail.
- **Regression**: остаётся 0 failures (Phases 1–6).

---

## 15. Honest Assessment

**Почему это лучше текущего (хардкод в arch-gate)?**
Backstage/OPA/Google AIP доказали: governance работает только как version-controlled
data + automated check. Хардкод `ALLOWED` в тесте = governance в коде (anti-pattern
из раздела 6). AKB выносит LAW в данные — меняешь закон, не трогая тест.

**Что может оказаться ошибкой?**
- AKB распухнет и станет «мертвым docs» (никто не читает). Митигация: owner-ADR,
  automated enforcement (тесты fail при нарушении, а не при отсутствии doc).
- YAML vs markdown ADR рассинхрон. Митигация: yaml = индекс, не дубликат.

**Что бы изменил архитектор Google (AIP)?**
Сделал бы AKB-linter частью pre-commit hook (instant feedback, как API linter).
→ KROFT: AKB-2..4 как pytest, добавить в CI/pre-commit.

**Что бы изменил архитектор Backstage?**
Отделил бы «catalog» (akb/) от «UI» (vault render). KROFT: akb/ = data, vault md =
human view. ✅ уже так.

**Что бы изменил архитектор OPA?**
Не пихал бы Rego в runtime (нарушит LAW K8). KROFT: политики = YAML, проверка =
Python в tests/. ✅ соблюдено.

**Можно ли проще?**
Да — AKB-1 (только YAML, без enforcement-кода) даёт 60% ценности (Hermes может
читать при ревью). Enforcement (AKB-2..4) — надстройка.

**Можно ли модульнее?**
Да — каждый LAW/PATTERN = отдельный YAML-блок; добавляется без кода.

**Можно ли уменьшить связанность?**
LAW K8: AKB в docs/, НЕ импортируется runtime. Enforcement в tests/ (вне runtime).
Связанность минимальна.

**Вердикт**: синтез честен, опирается на 5 индустриальных прецедентов, не копирует
реализации (Backstage-портал не берём), соблюдает LAW K1–K8. AKB-1 (данные) можно
создать немедленно; enforcement — отдельная фаза. Рекомендуется к принятию как
ADR-022 и поэтапной реализации.
