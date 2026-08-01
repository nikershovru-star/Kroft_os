---
title: "KROFT_OS — Project Context Map"
version: "1.1"
date: "2026-08-01"
status: "active"
lang: ru
purpose: >
  Компактный архитектурный паспорт для AI-моделей и инженеров.
  Читается ПЕРЕД любой работой с кодом или документами.
  Содержит: слои, правила, статус, структуру, запреты.
  v1.1: audit vs диск (757 tests, arch-gate работает, ADR-025, F1-F6).
---

# KROFT_OS — Project Context Map v1.1

## 0. Что такое KROFT_OS

**KROFT_OS** (Knowledge Runtime & Orchestration Framework Technology Operating System) — инженерная операционная система для создания, управления и эволюции AI-агентов.

Это НЕ приложение и НЕ набор скриптов. Это **саморазвивающаяся инженерная платформа**, где знания, архитектура, код, решения и эксперименты связаны в единую систему.

Цель: среда, в которой AI-агенты исследуют, создают, хранят знания, проверяют архитектуру, выполняют задачи, анализируют ошибки и улучшают систему через контролируемую эволюцию.

---

## 1. Архитектурные слои (сверху вниз)

```
KP (Philosophy)
    ↓ рождает
LAW (Policy: K1-K8 + F1-F6 forbidden patterns)
    ↓ констреинит
KRM (Reference Model) — метамодель сущностей
    ↓ определяет сущности для
KERA (Engineering Reference Architecture) — конституция системы
    ↓ описывает слои
    CORE (kernel / runtime / contracts)
    SERVICE (Agent / Knowledge / Memory / Workflow / Evaluation / Security / Model Platforms)
    META (Research Mesh / AKB / Architecture Intelligence / Evolution Engine)
    ↓ методология изменений
KEH (Engineering Handbook)
    ↓ наука доказательств
KES (Engineering Science)
    ↓ универсальный словарь
KL (Language)
    ↓ предложения до принятия
RFC (Request for Comments)
    ↓ принятые решения
ADR (Architecture Decision Records) + AKB (Architecture Knowledge Base)
    ↓ исполняется в
Runtime / Applications
```

| Слой | Расшифровка | Файлы | Назначение |
|------|-------------|-------|------------|
| **KP** | Philosophy | `docs/architecture/KP/` | 7 принципов (Knowledge > Code, Evidence > Opinion, Architecture > Features, Small Kernel, Composable Systems, Humans Approve, Everything Measurable) |
| **KRM** | Reference Model | `docs/architecture/KRM/` | Метамодель: 16 entity-types (Knowledge, Artifact, Decision, Capability, Contract, Platform, Agent, Component, Signal, Boundary, State, Projection, Policy, Resource, Workflow, Evidence) |
| **KERA** | Engineering Reference Architecture | `docs/architecture/KERA/` | Конституция: 3 уровня (Core / Service / Meta), 6 Views (Logical, Runtime, Deployment, Knowledge, Security, Evolution) |
| **KEH** | Engineering Handbook | `docs/architecture/KEH/` | Как правильно менять систему: Research, ADR, Benchmark, Documentation, Review, Experiment Handbooks |
| **KES** | Engineering Science | `docs/architecture/KES/` | Как доказать правильность: Research Science, Decision Science, Benchmark Science, Reliability Science, Economics, Human Factors |
| **KL** | Language | `docs/architecture/KL/` | Убиквитарный язык: термины, определения, запрещённые синонимы |
| **RFC** | Request for Comments | `docs/architecture/RFC/` | Предложения до ADR. Статусы: draft → under_review → decided / rejected / superseded |
| **AKB** | Architecture Knowledge Base | `docs/architecture/AKB/` | Машиночитаемая память: YAML (laws, adrs, patterns, standards, glossary, rfcs, history, evidence_levels, org_memory, tech_catalog, pattern_library) |
| **ADR** | Architecture Decision Records | `docs/architecture/ADR-*.md` | Принятые решения. ADR-001..025. Плоское хранение (не в подпапке), имена с пробелами |

---

## 2. Структура репозитория (Вариант Г)

```
KROFT_OS/                    ← главный git-репозиторий (будущий)
├── docs/
│   └── architecture/
│       ├── KP/  KRM/  KERA/  KEH/  KES/  KL/  RFC/  AKB/   ← 8 подпапок (см. §1)
│       ├── ADR-001.md .. ADR-025.md                     ← плоские файлы (имена с пробелами)
│       ├── Architecture Review.md
│       └── Kernel Review.md
├── kernel/  contracts/  runtime/  services/  adapters/
├── cli/  infrastructure/  plugins/  policies/  tests/  main.py  bootstrap_v2.py
```

**Важно — раздвоение на данный момент:**
- **Код** физически в `KnowledgeOS-v5/` (34M git-репо, 757 passed / 19 skipped).
- **Доки** в `KROFT_OS/docs/` (не git, вне репо).
- Слияние в единый `KROFT_OS/` — следующий этап (Variant Г: копирование 271 файла, исключая data/*.exe/.hermes/cache).
- Local git remote ОТСУТСТВУЕТ — коммиты только локальные, `git push` запрещён.

---

## 3. Архитектурные законы (LAW K1–K8 + F1–F6)

Источник: `docs/architecture/AKB/laws.yaml` + `AKB/patterns/forbidden.yaml`.
Читаются Architecture Gate (`tests/test_architecture.py`). Нарушение K-закона = block.

| ID | Закон | Суть | Severity |
|----|-------|------|----------|
| **K1** | `kernel-imports-only-contracts` | Ядро импортирует ТОЛЬКО `contracts/`. Никогда `services/`, `adapters/`, `infrastructure/` | block |
| **K2** | `services-dont-modify-kernel` | Сервисы НЕ модифицируют ядро. Расширение только через порты | block |
| **K3** | `kernel-does-not-know-services` | Ядро не знает о конкретных сервисах. Связка только в Composition Root (`bootstrap_v2`) | block |
| **K4** | `artifacts-traceable` | Каждый вывод агента — frozen + traceable (who, when, why) | warn |
| **K5** | `human-approve-required` | Критические изменения требуют подтверждения человека (deploy, ADR, self-improve) | block |
| **K6** | `explicit-boundaries` | Межслойное общение ТОЛЬКО через `contracts/` или EventBus. Никаких прямых вызовов через границу | block |
| **K7** | `atomic-commits` | Коммиты атомарны по фазе; `git add -A` запрещён; только поименованные файлы | warn |
| **K8** | `architecture-intelligence-outside-runtime` | Интеллект (AKB, Research Mesh, LLM) живёт в `docs/` + `services/`, НИКОГДА в `runtime/` или `kernel/` | block |

**Forbidden Patterns (F1–F6)** — автоматически ловятся arch-гейтом:

| ID | Паттерн | Суть |
|----|---------|------|
| **F1** | `blocking-sleep-in-recovery` | Блокирующий sleep в recovery-цикле ядра |
| **F2** | `runtime-imports-services` | runtime/ импортирует services/ (нарушение K1/K3) |
| **F3** | `hardcoded-dependency-in-kernel` | хардкод зависимости в kernel/ |
| **F4** | `meta-layer-in-runtime` | мета-слой (AKB/LLM) в runtime/ (нарушение K8) |
| **F5** | `untraceable-agent-result` | AgentResult без trace (нарушение K4) |
| **F6** | `adr-without-evidence` | ADR без уровня доказательства (KES#1) |

---

## 4. Ключевые ADR (ADR-001..025)

Источник: `docs/architecture/ADR-*.md` + `AKB/adrs.yaml`.

| ADR | Тема | Статус | Законы |
|-----|------|--------|--------|
| ADR-001 | Kernel | accepted | K1, K3 |
| ADR-002 | Contracts | accepted | K1 |
| ADR-003 | Event Bus | accepted | K1, K6 |
| ADR-009 | Policy Platform (итоговый; ADR-007 помечен Superseded) | accepted | K3, K5 |
| ADR-010 | Evaluation Platform | accepted | K4 |
| ADR-011 | Knowledge Platform | accepted | K1, K2 |
| ADR-012 | Memory Platform | accepted | K1, K2 |
| ADR-013 | Workflow Platform | accepted | K3, K4 |
| ADR-014 | Agent Platform | accepted | K4, K5, K8 |
| ADR-020 | Runtime Evolution | accepted | K1, K3, K8 |
| ADR-021 | Architecture Intelligence Synthesis | accepted | K1, K8 |
| ADR-022 | AKB (machine-readable governance) | accepted | K8 |
| ADR-023 | Agent Hierarchy & Research Mesh | accepted | K1, K3, K4, K5, K8 |
| ADR-024 | Meta Engine & EIP | accepted | K3, K8 |
| **ADR-025** | **Multimodal Knowledge Engine (PHASE 6)** | **proposed** | K8, K4, K3 |

> Примечание: ADR-007 существует в двух редакциях (`ADR-007 Policy Platform — Design.md` и `ADR-007 Policy Platform — Superseded by ADR-009.md`). Итоговый — ADR-009.

---

## 5. Убиквитарный язык (KL) — ключевые термины

Источник: `docs/architecture/AKB/glossary.yaml`.

| Термин | Определение | Запрещённые синонимы |
|--------|-------------|---------------------|
| **Agent** | Автономный компонент, реализующий `IAgentPlatform`; выполняет goal → AgentResult | Worker, Executor, Assistant, Bot |
| **Platform** | Крупная подсистема экосистемы (Research/Runtime/Knowledge/...) | Subsystem, Service-layer |
| **Kernel** | Минимальное ядро (`kernel/` + `runtime/`), импортирует только `contracts/` | Core, Engine |
| **Capability** | Атомарная функция, предоставляемая компонентом через порт | Feature, Function |
| **Research** | Сбор и синтез инженерных знаний (Research Mesh) | Investigation, Study |
| **Evidence** | Доказательство с Evidence Level (I–V, KES#1) | Proof, Source |
| **Artifact** | Persist-вывод агента/процесса | Output, Result |
| **Knowledge** | Накопленные инженерные знания (AKB + Knowledge Platform) | Data, Info |
| **Loop** | Замкнутый feedback-контур EIP | Cycle, Pipeline |
| **Composition Root** | Точка сборки компонентов (`bootstrap_v2`) | Wiring, Bootstrap |
| **Experiment** | Контролируемое изменение (Hypothesis → Metrics → Result) | Test, Trial |

**Правило:** один термин = одно понятие. Синонимы запрещены.

---

## 6. Текущий статус (audit 2026-08-01)

### ✅ Готово
- [x] KP Philosophy (7 принципов)
- [x] KL Language + Glossary (glossary.yaml)
- [x] RFC Layer (rfcs.yaml)
- [x] KERA Views (6 представлений)
- [x] KEH / KES restructuring (MOC-навигация)
- [x] AKB model (13 YAML + patterns/standards)
- [x] KRM v1.0 (16 entity-types)
- [x] Docs reorg в подпапки (KP/KRM/KERA/KEH/KES/KL/RFC/AKB)
- [x] **Architecture Gate — РАБОТАЕТ** (`tests/test_architecture.py` → 3 passed, ловит K1–K8 + F1–F6)

### 🔢 Метрики (реальный прогон)
- **Tests:** `757 passed, 19 skipped` (KnowledgeOS-v5, 2026-08-01)
- **Arch-gate:** `3 passed` (K1–K8 + F1–F6 clean)
- **ADR:** 25 (ADR-001..025), из них ADR-025 — proposed

### 🔜 Впереди
- [ ] Knowledge Graph v2 (связи между ADR/Component/Experiment)
- [ ] Architecture Intelligence (Hermes v2.0) — частично (ADR-021/023/024)
- [ ] Runtime self-analysis
- [ ] Code migration: KnowledgeOS-v5 → KROFT_OS/ (Variant Г, единый репо)
- [ ] CI/CD pipeline
- [ ] PROJECT_CONTEXT_MAP.md → MOC-интеграция (этот файл)
- [ ] **ADR-025 → accepted** (PHASE 6 Multimodal: код MK-001..005 ещё не написан)

---

## 7. Правила для AI-моделей (обязательны к исполнению)

### ДЕЛАТЬ
1. **Анализируй** существующую архитектуру ПЕРЕД написанием кода.
2. **Проверяй** KP / KERA / KL перед любыми изменениями.
3. **Ищи** существующие решения в AKB (`laws.yaml`, `adrs.yaml`, `pattern_library.yaml`).
4. **Предлагай** RFC перед большими изменениями.
5. **Создавай** ADR после принятия решения (с Evidence Level, KES#1).
6. **Храни** знания после изменений (update AKB, history, org_memory).
7. **Прогоняй arch-gate** (`tests/test_architecture.py`) перед коммитом волны.

### НЕ ДЕЛАТЬ
1. **НЕ** пиши код без проверки архитектуры.
2. **НЕ** создавай новые термины без обновления KL (glossary.yaml).
3. **НЕ** создавай ADR без RFC для больших изменений.
4. **НЕ** добавляй сервисы в `kernel/` (LAW K1/K3).
5. **НЕ** смешивай `docs/` и `runtime/` (LAW K8).
6. **НЕ** используй `git add -A` (LAW K7).
7. **НЕ** нарушай границы слоёв (LAW K6).
8. **НЕ** делай `git push` — remote отсутствует, коммиты локальны.

---

## 8. Как читать этот файл (MOC)

- **Новая модель / инженер:** раздел 0 → 3 (LAW) → 7 (правила).
- **Архитектор:** 1 (слои) → 2 (структура) → 4 (ADR) → 6 (статус).
- **Разработчик:** 5 (KL) → 3 (LAW) → 7 (DO/DON'T).
- **Исследователь:** 1 → KES/KEH → AKB/org_memory.yaml.

---

## 9. Связанные файлы (must-read при глубокой работе)

| Задача | Файлы |
|--------|-------|
| Понять философию | `KP/KROFT Philosophy (KP).md` |
| Понять метамодель | `KRM/KROFT Reference Model (KRM) v1.0.md` |
| Понять архитектуру | `KERA/KROFT Engineering Reference Architecture (KERA) v1.0.md` + `KERA Views/*.md` |
| Проверить термин | `AKB/glossary.yaml` + `KL/KROFT Language (KL).md` |
| Проверить закон | `AKB/laws.yaml` + `AKB/patterns/forbidden.yaml` |
| Проверить решение | `ADR-*.md` + `AKB/adrs.yaml` + `AKB/org_memory.yaml` |
| Предложить изменение | `RFC/KROFT RFC Layer.md` + `KEH/KROFT Engineering Handbook (KEH).md` |
| Доказать решение | `KES/KROFT Engineering Science (KES).md` + `AKB/evidence_levels.yaml` |
| Найти шаблон | `AKB/pattern_library.yaml` + `AKB/patterns/allowed.yaml` |
| Проверить историю | `AKB/history.yaml` |

---

> **Запомни:** KROFT_OS строит не только код. Она строит организационную память. Код можно переписать. Потерянное знание «почему сделали так» — нет.
>
> **v1.1 changelog:** исправлены расхождения с диском — счётчик тестов (757/19), arch-gate помечен как работающий (3 passed), добавлен ADR-025 (proposed), добавлены F1–F6 forbidden patterns, уточнена структура docs (8 подпапок) и раздвоение код/docs.
