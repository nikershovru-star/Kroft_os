---
tags: [kroft, kera, reference-architecture, constitution, ecosystem, platforms, maturity, law]
created: 2026-08-01
author: Hermes (Architecture Intelligence — синтез ADR-021..024)
status: v1.0 (constitution — authoritative reference)
supersedes_fragmentation: [ADR-021, ADR-022, ADR-023, ADR-024]
purpose: >-
  Главный документ проекта («конституция»). Замыкает разрозненное формирование
  архитектурной картины (ADR-021..024) в единую систему координат. Новые ADR
  описывают ОТДЕЛЬНЫЕ решения В РАМКАХ KERA, а не формируют картину по частям.
---

# KROFT Engineering Reference Architecture (KERA) v1.0

> **Конституция проекта.** Версия 1.0. Дата: 2026-08-01.
> Автор: Hermes (Architecture Intelligence Protocol v2.0, синтез ADR-021..024).
> Статус: authoritative reference. Все последующие ADR ссылаются на KERA.

---

## 0. Как читать этот документ

KERA — не ADR и не план. Это **система координат**. Он отвечает на 5 вопросов:

1. **Миссия и границы** — что KROFT есть, а что — нет.
2. **Слои** — ядро / сервисы / метаслой (где что живёт, LAW K8).
3. **10 платформ экосистемы** — что вокруг ядра.
4. **Зрелость (L1–L18)** — насколько далеко мы продвинулись.
5. **Законы (LAW K1–K8)** — как оценивать любое решение (lenses).

После KERA новые ADR = локальные решения внутри этой картины. KERA сам меняется
только через **meta-решение** (ADR уровня KERA), не инкрементально.

---

## 1. Миссия и границы

### 1.1 Миссия
KROFT — **автономная операционная система для инженерной организации** (Engineering
Organization OS). Не «ОС для агентов» (это подмножество), а OS для всей инженерии:
архитектура хранится как знания, исследования идут постоянно, решения объяснимы через
ADR и организационную память, код/тесты/документация/эксперименты — единый жизненный
цикл, люди и AI работают в общем процессе с понятными границами ответственности.

### 1.2 Границы (что KROFT НЕ есть)
- ❌ **НЕ монолитный runtime с LLM-рассуждением внутри.** Runtime минимален (LAW K8).
- ❌ **НЕ внешний оркестратор агентов** (LangGraph и т.п.) — агенты KROFT-нативны.
- ❌ **НЕ замена людям** — Human-in-the-loop обязателен для apply/approve (LAW K5/K7).
- ❌ **НЕ ML-платформа прогнозов** — forecasting начинает с heuristic (Sculley warning).
- ❌ **НЕ документация-ради-документации** — AKB enforcement через тесты, не присутствие doc.

### 1.3 Stakeholder viewpoints (по OASIS RA)
| Viewpoint | Кого касается | Главная забота |
|---|---|---|
| Core | Kernel devs | Минимальность, LAW K3/K8, стабильные порты |
| Services | Platform teams | IAgentPlatform-реализации, composition root |
| Meta-layer | Hermes / Architect | EIP контуры, AKB как source of truth |
| Human | Организация | Объяснимость решений, approve-границы |

---

## 2. Три слоя (Core / Services / Meta-layer)

KROFT — трёхслойная система. Каждый слой имеет строгие границы импортов (LAW K1–K8).

```
┌─────────────────────────────────────────────────────────────┐
│  META-LAYER  (Engineering Intelligence Platform, EIP)         │
│  Hermes + Research Mesh agents (services/) + AKB (docs/)      │
│  НЕ runtime/. Живёт ВНЕ ядра. Использует KROFT как substrate.│
├─────────────────────────────────────────────────────────────┤
│  SERVICES    (Platforms P1–P10 как components/services)       │
│  IAgentPlatform impls, agents, integrations, marketplace      │
│  Импортируют contracts + runtime (через порты), НЕ наоборот.  │
├─────────────────────────────────────────────────────────────┤
│  CORE        (Kernel + runtime/ — минимальное ядро)           │
│  Kernel, ComponentRegistry, Supervisor, EventBus, Recovery     │
│  Импортирует ТОЛЬКО contracts (LAW K1).                       │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Core (ядро)
- **Что**: `kernel/` (IKernel, lifecycle), `runtime/` (ComponentController,
  Supervisor, Recovery, EventBus, HotReload, ConfigService).
- **Правило**: импортирует ТОЛЬКО `contracts.*` + stdlib (LAW K1, K8). НЕ импортирует
  services/adapters/plugins/agents.
- **DoD**: `python -m runtime` → Kernel READY; arch-gate зелёный; 0 regression.

### 2.2 Services (сервисы)
- **Что**: `services/` (AgentService, MemoryService, ...), `adapters/`, `plugins/`,
  `platforms/` (волны 11–14), Research Mesh agents, Marketplace items.
- **Правило**: реализуют порты из `contracts/`; НЕ модифицируют ядро (LAW K3); могут
  импортировать contracts + runtime (через порты), но НЕ runtime-импорт в обратную
  сторону.
- **DoD**: порт стабилен, компонент activation через ComponentRegistry.

### 2.3 Meta-layer (метаслой / EIP)
- **Что**: Hermes (orchestrator вне кода), `docs/architecture/akb/` (machine-readable
  knowledge), Research Mesh agents (как IAgentPlatform-компоненты в services/).
- **Правило**: НЕ в `runtime/`. Читает/пишет AKB (docs). Enforcement через `tests/`
  (arch-gate, будущие adr_compliance/patterns). External LLM (OmniRoute) — ВНЕ domain.
- **DoD**: AKB валиден (YAML parse); arch-gate читает laws.yaml; PR-check блокирует K-нарушения.

---

## 3. Engineering Intelligence Platform (EIP) — 3 контура

EIP = мета-оркестрация поверх слоёв. 3 контура как независимые feedback loops,
связанные через KROFT EventBus (ADR-003, уже есть).

```
              Engineering Intelligence Platform (EIP)
                          │
      ┌───────────────────┼───────────────────┐
      ▼                   ▼                   ▼
 RESEARCH          ARCHITECTURE         DEVELOPMENT
 (P1 Research)     (P2 Architecture)    (P3 Development)
      │                   │                   │
      ▼                   ▼                   ▼
 RUNTIME           KNOWLEDGE           INTELLIGENCE
 (P4 Runtime)      (P5 Knowledge)      (P6 Intelligence)
      │                   │                   │
      ▼                   ▼                   ▼
 OPERATIONS        COLLABORATION        MARKETPLACE
 (P7 Ops)          (P8 Collaboration)   (P9 Marketplace)
                    │
                    ▼
             EVOLUTION PLATFORM (P10)
        (Continuous Research/Refactor/Learning/Bench/Governance)
```

Контуры:
- **Research Loop**: Research Mesh → AKB (knowledge). Источник: GitHub/Arxiv/RFC/Blogs/Security/Benchmarks/Standards.
- **Architecture Loop**: Reviewer + Simulator + Risk + ADR Engine → ADR Generator. Опирается на AKB (Уровень 3).
- **Implementation Loop**: Planning → Code → Tests → CI → Release. Golden path = composition root (bootstrap_v2).
- **Learning Loop**: Experiment Engine + Org Memory + Meta Engine → AKB Update. Замыкает цикл.

---

## 4. 10 платформ экосистемы

| # | Платформа | Слой | Статус в KROFT | Якорь |
|---|---|---|---|---|
| P1 | Research Platform | Meta | 🟡 зачаток (ADR-023 RM) | Research Mesh → AKB |
| P2 | Architecture Platform | Meta | 🟡 ADR Engine/Simulator нет | ADR-021/022/023/024 |
| P3 | Development Platform | Services | ❌ SDLC не автоматизирован | bootstrap_v2 (golden path) |
| P4 | Runtime Platform | Core | ✅ Phases 1–5 закрыты | ADR-020 Kernel/Registry/Supervisor |
| P5 | Knowledge Platform | Meta | 🟡 AKB есть, не полный | ADR-022 AKB (10 YAML) |
| P6 | Intelligence Platform | Meta | ❌ CTO-агент не собран | ADR-023/024 L10/L18 |
| P7 | Operations Platform | Services | 🟡 Recovery/Config есть | ADR-020 Phase 4/5 |
| P8 | Collaboration Platform | Services | ❌ human/AI boundary не формализован | LAW K5/K7 (approve) |
| P9 | Marketplace Platform | Services | ❌ catalog не реализован | Plugin Pattern (PL2) |
| P10 | Evolution Platform | Meta | ❌ continuous-* не собран | ADR-024 L11/L13/L14/L16 |

**Mapping платформ → реальный код KROFT:**
- P4 = `kernel/` + `runtime/` + `contracts/` (IAgentPlatform, IComponentController).
- P5 = `docs/architecture/akb/` (laws/adrs/patterns/tech_catalog/org_memory/history).
- P1/P2/P6 = будущие agents (services/), реализующие IAgentPlatform.
- P3/P7/P8/P9/P10 = evolution roadmap (не в runtime).

---

## 5. Зрелость (L1–L18)

Лестница зрелости архитектурного агента. KROFT реально сейчас: **L1/L3 ✅, L12/L17 🟡, остальное — roadmap**.

| L | Название | Суть | Статус |
|---|---|---|---|
| L1 | Intelligence | Исследование мировых практик | ✅ ADR-021/022/023/024 |
| L2 | Reviewer | Самокритика архитектуры | 🟡 arch-gate static |
| L3 | Knowledge Base | Инженерная память (ADR + причины) | ✅ AKB (ADR-022) |
| L4 | Pattern Library | Удачный компонент → шаблон | 🟡 pattern_library.yaml (PL1–PL10) |
| L5 | Simulator | Цифровой двойник (what-if) | ❌ |
| L6 | Tech Debt Engine | Авто-подсчёт долга + рейтинг | 🟡 arch-gate partial |
| L7 | Evolution Engine | Рефакторинг при новых знаниях | ❌ |
| L8 | Autonomous Architect | Сам ищет RFC/статьи еженедельно | ❌ |
| L9 | Benchmark Lab | A/B реализаций | ❌ |
| L10 | AI Chief Architect | Замкнутый конвейер | ❌ |
| L11 | Meta Architecture Engine | Как эволюционирует САМА архитектура | ❌ |
| L12 | Governance | Любой PR через Hermes + K-проверка | 🟡 arch-gate (PR-check planned) |
| L13 | Continuous Research | Research Mesh как сервис | ❌ |
| L14 | Forecasting | Прогноз арх-проблем | ❌ |
| L15 | Experiment Engine | Проверка, а не «что лучше?» | ❌ |
| L16 | Self-Improving | Улучшает свои процессы | ❌ |
| L17 | Organizational Memory | Почему + кто + ошибки + пересмотр | 🟡 org_memory.yaml (ADR-E) |
| L18 | Autonomous CTO | Полный конвейер Idea→KB Update | ❌ |

---

## 6. Законы архитектуры (LAW K1–K8) как lenses

LAW — это **evaluative lenses** (по AWS Well-Architected): любое решение оценивается
через них. Точные формулировки — в `docs/architecture/akb/laws.yaml` (source of truth).

| LAW | Суть | Lens (вопрос при ревью) |
|---|---|---|
| K1 | Kernel импортирует только contracts | «Не лезет ли ядро в сервисы?» |
| K2 | Domain зависит от contracts, не наоборот | «Нет ли обратной зависимости?» |
| K3 | Kernel НЕ модифицируется платформами | «Меняем ли мы ядро для фичи?» |
| K4 | Решения traceable (AgentResult frozen) | «Можно ли восстановить ход решения?» |
| K5 | Human approve для apply | «Есть ли человек в контуре approve?» |
| K6 | Failures — данные, не исключения | «Обрабатываем ли сбой как данные?» |
| K7 | Atomic commits, НЕ git add -A | «Коммит атомарен и поименован?» |
| K8 | runtime/* импортирует ТОЛЬКО contracts + stdlib | «Не попал ли LLM/agent в runtime?» |

**Развитие LAW:** новые законы добавляются ТОЛЬКО через ADR (meta-решение) и заносятся
в `laws.yaml`. Старые LAW пересматриваются через Meta Architecture Engine (L11) — НЕ
тихо. Пример кандидата: **K9 (Observability-by-default)** — каждый компонент публикует
метрики в EventBus (обсуждается, НЕ принят).

---

## 7. Модель взаимодействия (Runtime ↔ Services ↔ Research Mesh ↔ AKB ↔ External LLM)

```
┌──────────────┐    ports     ┌──────────────┐
│   CORE       │◄────────────►│  SERVICES    │  (IAgentPlatform impls, agents)
│  runtime/    │  (contracts) │  services/   │
└──────┬───────┘              └──────┬───────┘
       │ EventBus (ADR-003)          │ EventBus
       ▼                             ▼
┌──────────────┐              ┌──────────────┐
│  AKB (docs/) │◄── read/write┤ Research Mesh │  (meta-layer, IAgentPlatform agents)
│ laws/adrs/   │              │ Code/Paper/  │
│ org_memory/  │              │ Docs/Bench/  │
└──────┬───────┘              │ Sec agents   │
       │                      └──────┬───────┘
       │ RAG context                 │ synthesize (RAG over AKB)
       ▼                             ▼
┌──────────────┐              ┌──────────────┐
│ EXTERNAL LLM │◄────────────►│  Hermes      │  (orchestrator, вне кода)
│ OmniRoute    │  base_url    │  (EIP)       │
└──────────────┘  ONLY        └──────────────┘
```

**Ключевые инварианты:**
1. External LLM (OmniRoute) — ВНЕ domain-слоя, только `base_url` (не импорт) (memory).
2. Research Mesh читает AKB (RAG) → убирает галлюцинации зависимостей (arxiv).
3. AKB — data, не код; читается Hermes и tests/, НЕ импортируется runtime (LAW K8).
4. Ядро НЕ знает про LLM/agents (LAW K1/K3). Agents — компоненты (services/).

---

## 8. Governance модель (как новые ADR попадают в картину)

1. Любое решение, меняющее границу слоя / добавляющее LAW / новую платформу → **ADR**.
2. ADR пишется в `docs/architecture/`, регистрируется в `akb/adrs.yaml` (индекс).
3. ADR проверяется на соответствие KERA (L1–L18 mapping, LAW K1–K8, слой).
4. Принятый ADR → atomic commit + обновление `akb/history.yaml` (Knowledge Base Update).
5. Изменения LAW → только через meta-ADR (KERA-level), НЕ тихо.
6. PR-check (L12, planned): arch-gate читает `laws.yaml`, блокирует K-нарушения до merge.

---

## 9. Текущий статус (snapshot 2026-08-01)

- **Core**: Phases 1–5 закрыты (Kernel READY, ComponentRegistry, Supervisor, HotReload,
  ConfigService). arch-gate зелёный, 750 passed + 6 pre-existing (Track L).
- **AKB (P5/L3)**: 10 валидных YAML (laws/adrs/patterns/tech_catalog/org_memory/history/
  pattern_library). Enabler для L2/L5/L12/L17.
- **ADR**: 021 (Evolution), 022 (AKB), 023 (Agent Hierarchy+Mesh), 024 (Meta+EIP) — proposed.
- **Gap до полной KERA**: P1/P2/P3/P6/P7/P8/P9/P10 частично/нет; L4–L11,L13–L18 roadmap.

---

## 10. Честная оценка (Self-Critique KERA)

- **Почему KERA, а не ADR-025**: ты верно диагностировал — картина формировалась по
  частям (ADR-021..024). KERA = консолидирующая «конституция», устраняющая фрагментацию.
- **Риск (честно)**: KERA может стать «мертвым doc». Митигация: он опирается на AKB
  (machine-readable) + arch-gate (enforcement), не на prose. KERA меняется только через
  meta-ADR.
- **Риск over-engineering**: 10 платформ + 18 уровней — амбициозно. Митигация: KROFT
  УЖЕ имеет substrate (Kernel/Registry/Supervisor/Bus/IAgentPlatform/AKB) для большинства.
  Roadmap последователен (L4→RM→L5→...→L18).
- **LAW K8 соблюдён**: EIP/agents/LLM — вне runtime. Ядро минимально.
- **Отличие от индустрии**: CNCF/Backstage — тяжёлые порталы; KROFT EIP = лёгкий YAML +
  существующий arch-gate + KROFT-native agents. Не копируем Backstage, берём паттерн.

---

## 11. Что дальше (после KERA)

KERA принят как конституция. Следующие шаги — локальные ADR/фазы ВНУТРИ KERA:
1. **L12 (Governance)**: PR-check (arch-gate читает laws.yaml) — высокий приоритет.
2. **AKB-2..4 (ADR-022)**: arch-gate → YAML; test_adr_compliance; test_patterns.
3. **RM-1..4 (ADR-023)**: Research Mesh agents (KROFT-native).
4. **L4/L5/L6** (Pattern/Simulator/TD) — по плану ADR-023/024.

KERA НЕ переписывается инкрементально. Только meta-ADR уровня KERA.

---
*KERA v1.0 — конец конституции. Новые ADR: ссылайся на разделы 3/4/5/6.*
