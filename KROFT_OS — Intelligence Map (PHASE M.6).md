---
tags:
  - kroft
  - architecture
  - status
  - intelligence-map
---

# KROFT_OS — Intelligence Map (State: PHASE M.6)

Интеллектуальная карта KROFT_OS по фактическому состоянию: что уже стало ядром, что является заготовкой, и что даст следующий скачок.

## Общая структура

```
                         ┌──────────────────────┐
                         │       KROFT_OS        │
                         │ Cognitive Operating   │
                         │       System          │
                         └──────────┬───────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│ Cognitive Core │       │ Knowledge System │       │ Runtime System   │
│                │       │                  │       │                  │
│ Reasoning      │       │ Memory           │       │ Execution        │
│ Planning       │       │ Graph            │       │ Adaptation       │
└────────────────┘       └──────────────────┘       └──────────────────┘
```

---

## 1. COGNITIVE CORE — МОЗГ

**Статус:** 🟢 75–80% реализовано

```
Intent
  |
  ▼
Planner
  |
  ▼
Plan
  |
  ▼
Decision
  |
  ▼
ExecutionOutcome
  |
  ▼
Episode
  |
  ▼
Reflection
```

**Уже есть:**
- ✅ Intent System — вход пользователя, задача, confidence, provenance
- ✅ Planning — `Plan` (id, goal_id, steps, provenance)

**Есть, но неполное:**
- ❌ Plan пока не знает, какой Skill его выполняет.
  ```
  Сейчас:                     Нужно:
  Plan                        Plan
   |                           |
   steps=("search",           steps=("search",
          "analyze",                  "analyze",
          "answer")                   "answer")
        ?                       Procedure
                                    steps=("search",
                                           "analyze",
                                           "answer")
  Связь только через текст.
  ```
- ✅ Episode Memory — `Episode` (id, summary, confidence, provenance) — работает.
  ```
  ❌ episode ещё слабый как опыт.
  Нужно:
  Episode
   ├ situation
   ├ decision
   ├ action
   ├ result
   ├ mistake
   └ lesson
  То есть перейти: от "записи события" → к "опыту".
  ```

---

## 2. KNOWLEDGEOS — ПАМЯТЬ

**Статус:** 🟢 85% — одна из самых сильных частей.

```
                Vault
                  |
                  ▼
             Reader Layer
                  |
                  ▼
          KnowledgeDocument
                  |
                  ▼
              Chunking
                  |
                  ▼
            KnowledgeNode
                  |
       ┌──────────┴──────────┐
       ▼                     ▼
 Semantic Memory       Knowledge Graph
                        (Links/Wikilinks)
 FAISS
```

**Реализовано:**
- ✅ Obsidian Vault Integration — сканирование, чтение markdown, индексация.
  - Статистика: ~1500 файлов, ~1400 semantic vectors
- ✅ Semantic Memory — FAISS + MiniLM embeddings — работает
- ✅ Knowledge Graph — примерно 150 nodes, 320 links; связи, wikilinks, backlinks

**Нужно добавить:**
```
Сейчас:                            Нужно:
прочитал                           прочитал
  ↓                                  ↓
нашёл                            понял
  ↓                                  ↓
связал                           объединил
                                    ↓
                               создал концепт
                                    ↓
                               обновил карту знаний
→ Knowledge Consolidation Engine / Knowledge Archaeologist
```

---

## 3. PROCEDURAL MEMORY — НАВЫКИ

**Статус:** 🟡 60%

```
Сейчас:
Procedure (skill_id, capability, steps, confidence, version, lifecycle)

Skill Evolution:
ExecutionOutcome → SkillEvolver → Procedure improvement
```

KROFT уже умеет не просто хранить знания, а менять свои процедуры.

**Проблема:**
```
Сейчас:                  Нужно (следующий уровень):
Plan                     Skill Registry
  |                        |
  | ?                      ▼
  |                     Skill ID
Procedure                 |
                         Plan
                            |
                            ▼
                         Procedure
Нет Plan.skill_id → используется steps matching.
```

Но НЕ сейчас — потребует изменения контрактов. K6 пока правильно запрещает.

---

## 4. RUNTIME SUPERVISOR — САМОКОНТРОЛЬ

**Статус:** 🟢 70%

```
CognitiveKernel
       |
       ▼
RuntimeSupervisor
       |
       ▼
Metrics
       |
       ▼
TuningProposal
```

**Реализовано:** ✅ hook внутри kernel, ✅ подключение через composition, ✅ LiveMetricsCollector

**Проблема:**
```
Сейчас:                    Нужно:
Executor                   Real Execution
  ↓                          │
success=True                 ▼
  ↓                       Failure
Supervisor                  │
"всё хорошо"                ▼
                          Reflection
                              │
                              ▼
                          Supervisor
                              │
                              ▼
                          Correction
Система не получает настоящие ошибки.
```

---

## 5. EXECUTION LAYER — ГЛАВНЫЙ ПРОБЕЛ

**Статус:** 🔴 30%

```
Сейчас (симуляция):           Настоящая ОС:
Intent                         Intent
  ↓                              ↓
Plan                            Plan
  ↓                              ↓
Proxy Executor                  Agent Runtime
  ↓                              │
Success                         ├── tools
                                ├── browser
                                ├── code
                                ├── filesystem
                                └── external APIs
                                      │
                                      ▼
                                 Real Outcome
```

Главный недостающий слой.

---

## 6. MULTI-AGENT SYSTEM

**Статус:** 🟡 40%

Есть идеи: агенты, MCP, инструменты, Hermes. Пока нет полноценной Agent Runtime Fabric.

```
                Kernel
                  │
             Agent Runtime
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
 Research      Coding       Memory
 Agent         Agent        Agent
```

---

## 7. OBSERVABILITY

**Статус:** 🟢 80%

Есть: metrics, cache, latency, health, verification. База хорошая.

**Добавить — Cognitive Trace:**
```
User request
  ↓
Thought path
  ↓
Memory used
  ↓
Skill selected
  ↓
Tool used
  ↓
Result
  ↓
Lesson learned
```
«Чёрный ящик мозга».

---

## 8. SECURITY / PRIVACY

**Статус:** 🔴 20%

Важно, потому что другие люди подключают свой Obsidian.

Сейчас нет: user isolation, permission layer, private memory boundary.

```
KROFT Core
   │
   ▼
Multi Tenant Layer
   │
 ┌─────┼─────┐
User A User B User C
каждый: свой Vault, свои знания, свои модели
```

---

## 9. ФИНАЛЬНАЯ КАРТА РАЗВИТИЯ

```
                 KROFT_OS
                    🧠
              Cognitive Kernel
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
 KnowledgeOS   Skill System   Runtime
    🟢             🟡           🟡
    |              |             |
 Memory       Evolution     Supervisor
 Graph        Skills        Metrics
                    │
                    ▼
             EXECUTION ENGINE
                    🔴
                    │
        Tools / Agents / APIs
                    │
                    ▼
             AUTONOMOUS LOOP
 Observe → Think → Act → Measure → Learn → Improve
```

### Приоритеты добавления (порядок)

| Phase | Название | Приоритет |
|-------|----------|-----------|
| **PHASE N** | Execution Layer — настоящий Executor, Agent Runtime, реальные outcomes | ⭐⭐⭐⭐⭐ |
| **PHASE O** | Experience Memory — улучшить Episode: из события → опыт | ⭐⭐⭐⭐ |
| **PHASE P** | Agent Runtime — мультиагентная среда | ⭐⭐⭐⭐ |
| **PHASE Q** | Skill Registry — точный plan→skill | ⭐⭐⭐ |
| **PHASE R** | Personal/Enterprise Isolation — если хочешь давать KROFT другим людям | ⭐⭐⭐⭐⭐ |

---

## Оценка зрелости KROFT_OS сейчас

Если считать как настоящую AI-OS:

| Система | Состояние |
|---------|-----------|
| Kernel | 80% |
| Memory | 85% |
| Knowledge Graph | 75% |
| Skill Evolution | 60% |
| Runtime Adaptation | 70% |
| Execution | 30% |
| Multi-agent | 40% |
| Security | 20% |
| Product readiness | 25% |

**Общая зрелость:** примерно 55–60%.

Самое важное: уже построена не оболочка вокруг LLM, а зачаток настоящей когнитивной архитектуры.

**Главный следующий переход:**
> от «система думает и анализирует» → к «система действует, получает ошибки и сама улучшает себя».

Именно для этого следующая большая фаза должна быть **Execution Layer / Agent Runtime**, а не новые знания.
