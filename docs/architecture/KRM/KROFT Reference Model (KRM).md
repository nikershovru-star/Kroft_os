---
tags: [kroft, krm, reference-model, metamodel, entities, relationships]
created: 2026-08-01
author: Hermes (Architecture Intelligence — по principal-review: слой между философией и архитектурой)
status: v1.0 (metamodel, стабилен как KP)
position: "KP → KRM → KERA (KRM определяет сущности, KERA строит архитектуру поверх)"
summary: >-
  KROFT Reference Model (KRM) — метамодель системы. НЕ описывает конкретную
  архитектуру (это KERA), а определяет ДОПУСТИМЫЕ СУЩНОСТИ и СВЯЗИ между ними.
  Entity-types: Knowledge, Artifact, Decision, Capability, Contract, Platform, Agent,
  Component, Signal, Boundary, State, Projection, Policy, Resource, Workflow, Evidence.
  KERA строится поверх KRM. Делает архитектуру устойчивой к изменениям.
---

# KROFT Reference Model (KRM) v1.0

> **Метамодель** (по principal-review). KP → **KRM** → KERA. KRM отвечает: «Из каких
> фундаментальных сущностей состоит KROFT?» — и какие связи между ними ДОПУСТИМЫ.
> KERA уже строит конкретную архитектуру поверх этих сущностей. KRM стабилен (как KP).

---

## Entity-Types (фундаментальные сущности KROFT)

| # | Сущность | Определение (в KRM) | Пример в KROFT |
|---|---|---|---|
| RM-01 | **Knowledge** | Инженерное знание системы (не данные) | AKB, Org Memory, Glossary |
| RM-02 | **Artifact** | Persist-вывод процесса/агента (читаемый другими) | ResearchArtifact, AgentResult |
| RM-03 | **Decision** | Зафиксированное решение с метриками | ADR (adrs.yaml) |
| RM-04 | **Capability** | Атомарная функция через порт | IAgentPlatform.run |
| RM-05 | **Contract** | Порт (Protocol) в contracts/; граница слоя | IComponentController, IEventBus |
| RM-06 | **Platform** | Крупная подсистема экосистемы | Runtime/Knowledge/Agent Platform |
| RM-07 | **Agent** | Автономный компонент (IAgentPlatform) | Research Mesh agents |
| RM-08 | **Component** | Экземпляр в ComponentRegistry | Supervisor, ConfigService |
| RM-09 | **Signal** | Событие в EventBus (факт изменения) | `config.changed`, `component.failed` |
| RM-10 | **Boundary** | Граница слоя с правилами импортов | Core/Services/Meta (LAW K1/K8) |
| RM-11 | **State** | Состояние компонента (FSM) | ProcessState (INSTANTIATING→RUNNING...) |
| RM-12 | **Projection** | Взгляд на систему (View) | KERA Views (Logical/Runtime/...) |
| RM-13 | **Policy** | Правило поведения/безопасности | RecoveryPolicy, LAW K1–K8 |
| RM-14 | **Resource** | Физический/логический ресурс | CPU, memory, file handle |
| RM-15 | **Workflow** | Оркестрация шагов (IPlanner/IExecutor) | Workflow Platform (ADR-013) |
| RM-16 | **Evidence** | Доказательство с Evidence Level (I–V) | ResearchArtifact.evidence_level |
| RM-17 | **Media** | Мультимодальный источник знаний (video/audio/image/pdf/website/code) | YouTube video, PDF, podcast |
| RM-18 | **MediaNode** | Типизированный узел Knowledge Graph 2.0, порождённый Media (ADR-025) | VIDEO_NODE(Building AI Agents) |

---

## Allowed Relationships (допустимые связи)

```
KP ──generates──> LAW (Policy RM-13)
LAW ──constrains──> ADR (Decision RM-03)
ADR ──implemented_by──> Component (RM-08)
Component ──exposes──> Contract (RM-05)
Contract ──validated_by──> Benchmark (Artifact RM-02)
ADR ──justified_by──> Evidence (RM-16)
Evidence ──discussed_in──> RFC
Component ──measured_by──> Experiment
Component ──emits──> Signal (RM-09)
Signal ──updates──> Knowledge (RM-01)
Knowledge ──stored_in──> AKB
Platform (RM-06) ──composed_of──> Component (RM-08)
Agent (RM-07) ──realizes──> Capability (RM-04)
Boundary (RM-10) ──isolates──> Layer (Core/Services/Meta)
```

Это и есть **Knowledge Graph 2.0** (Этап 3): узлы = entity-types, рёбра = allowed relationships. Hermes отвечает: «Почему интерфейс X?» → traverses ADR→LAW→KP.

---

## Честная оценка (Self-Critique KRM)

- **Почему KRM нужен**: между философией (KP) и архитектурой (KERA) нет слоя
  сущностей. Без KRM KERA выглядит ad-hoc. KRM даёт словарь сущностей, из которых
  KERA собирает платформы/слои. Это делает архитектуру устойчивой (новая платформа =
  новая комбинация существующих entity-types, не новый вид).
- **Риск**: KRM может стать слишком абстрактным. Митигация: каждая сущность имеет
  конкретный пример в KROFT (колонка «Пример»). Абстракция без примера — запрещена.
- **Отличие от индустрии**: UML metaclass layering похож, но KRM специфичен для
  инженерной ОС ИИ (Evidence/Artifact/Decision как first-class сущности).
- **LAW K8**: KRM — docs, НЕ runtime. Читается Hermes + arch-gate (для валидации связей).
