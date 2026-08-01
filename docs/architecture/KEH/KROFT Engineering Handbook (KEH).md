---
tags: [kroft, keh, engineering-handbook, methodology, moc, navigation]
created: 2026-08-01
author: Hermes (Architecture Intelligence — реструктуризация: KEH = MOC методологии, не Bible)
status: v1.0 (navigation hub)
depends_on: [KP v1.0, KERA v1.0, KES v1.0, docs/architecture/akb/]
summary: >-
  KEH — MOC методологии (НЕ Engineering Bible). Навигация к Handbook'ам: Research,
  ADR, Benchmark, Documentation, Review, Experiment. Каждый Handbook — отдельный документ.
  KEH остаётся компактным; правила развиваются независимо per-handbook.
---

# KROFT Engineering Handbook (KEH) — MOC

> **KEH = навигация по методологии, а не сама методология** (по principal-review). Ранее
> KEH был «Engineering Bible» (опасно). Теперь KEH — hub к Handbook'ам. Каждый Handbook
> имеет свои правила, ссылается на KES-дисциплину. KEH не раздувается.

---

## Handbook'и (каждый — отдельный документ)

| Handbook | Документ | Суть | KES-связь |
|---|---|---|---|
| Research Handbook | [[KEH — Research Handbook]] | Процесс исследований, evidence-gate | Research Science |
| ADR Handbook | [[KEH — ADR Handbook]] | Методика оценки ADR, RFC→ADR | Decision Science |
| Benchmark Handbook | [[KEH — Benchmark Handbook]] | Требования к бенчмаркам | Benchmark Science |
| Documentation Handbook | [[KEH — Documentation Handbook]] | Стандарты документации, Glossary | Human Factors |
| Review Handbook | [[KEH — Review Handbook]] | Арх-ревью, Governance (PR-check) | Decision/Reliability |
| Experiment Handbook | [[KEH — Experiment Handbook]] | Правила экспериментов | Benchmark Science |

> Философия (KEH §1), правила изменения LAW (KEH §6), эволюция платформ (KEH §9) —
> остаются в этом MOC как кросс-секции (не выделены, т.к. стабильны).

---

## Принцип декомпозиции
- KEH (hub) меняется редко (добавление handbook = meta-решение).
- Handbook меняется при новых практиках (через ADR/RFC).
- Каждый handbook ссылается на KP (философию) и KES (науку).
- LAW K8: стандарты в AKB (docs/), НЕ runtime.

## Честная оценка
Разбиение решает твоё замечание (KEH 8.5/10 → выше): hub компактен, правила — в handbook'ах.
Risk рассинхрона устранён явными [[...]] ссылками. Отличие от индустрии: наши handbook'ы
машинночитаемы (AKB), не prose-only.
