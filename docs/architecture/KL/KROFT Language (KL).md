---
tags: [kroft, kl, language, vocabulary, ubiquitous-language, shared-terms]
created: 2026-08-01
author: Hermes (Architecture Intelligence — по principal-review: единый словарь)
status: v1.0 (foundational, evolves медленно через meta-ADR)
position: "KP → Vision → KERA → KEH → KES → AKB → ADR → ... → Runtime (КОНТУРЫ терминов)"
summary: >-
  KROFT Language (KL) — единый словарь (ubiquitous language, по DDD). Цель: чтобы
  Agent / Worker / Executor / Service / Module НЕ стали синонимами через 2 года.
  Machine-readable версия — docs/architecture/akb/glossary.yaml (проверяется линтером
  документации). Каждый термин: определение, aliases (запрещённые синонимы),
  used_in (где применяется).
---

# KROFT Language (KL) v1.0

> **Ubiquitous Language** (по DDD/Evans): единый словарь KROFT. Без него через 2 года
> `Agent`, `Worker`, `Executor`, `Assistant`, `Service`, `Module` окажутся одним и тем
> же → хаос. KL — контракт смыслов. Machine-readable версия: `akb/glossary.yaml`.

---

## Базовые термины (KL-001 .. KL-016)

| # | Термин | Определение | Запрещённые синонимы (aliases) |
|---|---|---|---|
| KL-001 | **Agent** | Автономный KROFT-компонент, реализующий IAgentPlatform; выполняет goal → AgentResult. | Worker, Executor (для agent), Assistant, Bot |
| KL-002 | **Platform** | Крупная подсистема экосистемы (P1–P10 в KERA): Research/Runtime/Knowledge/... | Subsystem (в контексте P*), Service-layer |
| KL-003 | **Kernel** | Минимальное ядро (kernel/ + runtime/), импортирует только contracts. | Core (как runtime), Engine |
| KL-004 | **Capability** | Атомарная функция, предоставляемая компонентом через порт. | Feature, Function (в контексте порта) |
| KL-005 | **Research** | Сбор и синтез инженерных знаний (Research Mesh). | Investigation, Study |
| KL-006 | **Evidence** | Доказательство утверждения с Evidence Level (I–V, KES#1). | Proof, Source (голое) |
| KL-007 | **Artifact** | Persist-вывод агента/процесса (читаемый другими). | Output, Result (голое) |
| KL-008 | **Knowledge** | Накопленные инженерные знания (AKB + Knowledge Platform). | Data (в контексте AKB), Info |
| KL-009 | **Loop** | Замкнутый feedback-контур EIP (Research/Architecture/Implementation/Learning). | Cycle, Pipeline (в контексте EIP) |
| KL-010 | **Composition Root** | Точка сборки компонентов (bootstrap_v2); единственное место wiring. | Wiring, Bootstrap (голое) |
| KL-011 | **Experiment** | Контролируемое изменение (Hypothesis→Metrics→Result). | Test (в контексте KES#3), Trial |
| KL-012 | **Contract** | Порт (Protocol/abstract) в contracts/; граница между слоями. | Interface (как реализация), API (как порт) |
| KL-013 | **Boundary** | Граница слоя (Core/Services/Meta) с правилами импортов (LAW K1/K8). | Layer (как boundary), Edge |
| KL-014 | **Projection** | Взгляд на систему (View в KERA: Logical/Runtime/Deployment/Knowledge/Security/Evolution). | View (как термин), Perspective |
| KL-015 | **Decision** | Зафиксированное решение (ADR) с score/confidence/risk. | Choice, Vote |
| KL-016 | **Signal** | Событие в EventBus (ADR-003), несущее факт изменения состояния. | Event (как термин), Message (низкоуровнево) |

---

## Правила использования (KL Governance)

1. В новых документах/коде используй ТОЛЬКО термины KL. Синонимы из `aliases` —
   запрещены (линтер документации флагует).
2. Новый термин → сначала в KL (meta-ADR), потом в использование. Не наоборот.
3. `aliases` фиксирует исторические дубликаты (напр. старый `Worker` → теперь `Agent`),
   чтобы не возникло расхождения.
4. KL меняется медленно (как KP), через meta-ADR. Chaos в терминах = chaos в архитектуре.

---

## Честная оценка (Self-Critique KL)

- **Почему KL нужен**: DDD доказал — ubiquitous language устраняет перевод между
  стейкхолдерами. В KROFT (где Hermes + люди + агенты) это критично: агенты должны
  понимать термины однозначно, иначе галлюцинации (KES#9).
- **Риск**: KL может отставать от практики. Митигация: glossary.yaml проверяется при
  каждом PR (док-lint), устаревший термин → warning.
- **Риск раздувания**: ограничен 16 базовыми (расширяется только meta-ADR).
- **LAW K8**: KL/Glossary — docs (AKB), НЕ runtime. Только doc-lint читает (как arch-gate).
