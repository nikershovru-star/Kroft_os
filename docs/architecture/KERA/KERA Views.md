---
tags: [kroft, kera, views, 4+1, logical, runtime, deployment, knowledge, security, evolution]
created: 2026-08-01
author: Hermes (Architecture Intelligence — по principal-review: KERA нужны Views)
status: v1.0 (navigation to views)
position: "KERA (конституция) → Views (адаптированный 4+1 по Kruchten)"
summary: >-
  KERA Views — адаптированная модель 4+1 (Kruchten) под KROFT: Logical, Runtime
  (process), Deployment (physical), Knowledge, Security, Evolution. KERA остаётся
  компактной; каждый View развивается отдельно. «Not all architectures need full 4+1»
  — берём релевантные для инженерной ОС.
---

# KERA — Views (адаптированный 4+1)

> KERA (конституция) описывает ЧТО такое KROFT. Views описывают его с разных сторон.
> По Kruchten 4+1: logical/development/process/physical + scenarios. Для KROFT
> адаптировано: Logical, Runtime (process), Deployment (physical), Knowledge, Security,
> Evolution. Каждый View — отдельный документ, развивается независимо.

---

## Список Views

| View | Вопрос | Аналог 4+1 | Документ |
|---|---|---|---|
| **Logical** | Из чего состоит система (компоненты, контракты)? | Logical | [[KERA View — Logical]] |
| **Runtime** | Как работает во время выполнения (процессы, события)? | Process | [[KERA View — Runtime]] |
| **Deployment** | Как развёрнута (узлы, топология)? | Physical | [[KERA View — Deployment]] |
| **Knowledge** | Где знания (AKB, Org Memory, Glossary)? | (KROFT-specific) | [[KERA View — Knowledge]] |
| **Security** | Границы, доверие, human-approve? | (cross-cutting) | [[KERA View — Security]] |
| **Evolution** | Как меняется (maturity L1–L18, meta-engine)? | (KROFT-specific) | [[KERA View — Evolution]] |

---

## Принцип Views

1. KERA = стабильное ядро (mission, слои, LAW, платформы). Views = детализация по сторонам.
2. View НЕ дублирует KERA; ссылается на разделы KERA.
3. View меняется чаще KERA, но медленнее ADR.
4. Неполный набор Views допустим («not all architectures need full 4+1»).
5. Scenarios (use cases) — связующее: критические пути иллюстрируют Views (опционально).

---

## Честная оценка

- **Почему Views**: KERA как один документ рискует стать «сборником всего» (та же
  ловушка, что KES/KEH). Views держат KERA компактной (10/10), детали — отдельно.
- **Риск**: рассинхрон View↔KERA. Митигация: View ссылается на KERA (single source).
- **Отличие от 4+1**: добавлены Knowledge/Security/Evolution (специфика инженерной ОС ИИ),
  убран Development (он в KEH/ADR, не в KERA).
