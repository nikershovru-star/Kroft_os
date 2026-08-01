---
tags: [kroft, kes, engineering-science, moc, navigation]
created: 2026-08-01
author: Hermes (Architecture Intelligence — реструктуризация: KES = MOC науки, не энциклопедия)
status: v1.0 (navigation hub)
depends_on: [KP v1.0, KERA v1.0, KEH v1.0, docs/architecture/akb/]
summary: >-
  KES — MOC науки (НЕ сама наука). Навигация к дисциплинам: Research Science,
  Decision Science, Benchmark Science, Reliability Science, Economics, Human Factors.
  Каждая дисциплина — отдельный документ, развивается независимо. KES остаётся компактным.
---

# KROFT Engineering Science (KES) — MOC

> **KES = навигация по науке, а не сама наука** (по principal-review). Ранее KES был
> одной «книгой» (380 стр) — это опасно. Теперь KES — hub, указывающий на дисциплины.
> Каждая дисциплина имеет свой документ, прецеденты и метод. KES не раздувается.

---

## Дисциплины (каждая — отдельный документ)

| Дисциплина | Документ | Суть | Прецедент |
|---|---|---|---|
| Research Science | [[KES — Research Science]] | Evidence Level I–V, consensus, reproducibility | Evidence-Based SE (Kitchenham) |
| Decision Science | [[KES — Decision Science]] | ADR measurable (score/confidence/risk) | MS Well-Architected confidence |
| Benchmark Science | [[KES — Benchmark Science]] | Reproducible benchmark (fixed env+seed) | SPEC RG / Henning |
| Reliability Science | [[KES — Reliability Science]] | Chaos, MTTR, fault isolation | Netflix FIT / arxiv 2412.01416 |
| Economics | [[KES — Economics]] | Cost of support/complexity/dependency | SEI TD Library / SIG |
| Human Factors | [[KES — Human Factors]] | Comprehension time, cognitive load | Cognitive complexity |

> AI Engineering Science и Engineering Theory (KES#9/#10) пока в этой MOC как
> направления; выделяются в отдельные документы при росте (не преждевременно).

---

## Принцип декомпозиции
- KES (hub) меняется редко (добавление дисциплины = meta-решение).
- Дисциплина-документ меняется при новых прецедентах/методах (через ADR/RFC).
- Каждая дисциплина ссылается на KP (откуда выведена) и KEH (где применяется).
- LAW K8: все данные (benchmarks/experiments) в AKB (docs/), НЕ runtime.

## Честная оценка
Разбиение решает твоё замечание (KES 8/10 → выше): hub компактен, детали — в дисциплинах.
Риск рассинхрона hub↔дисциплина устранён явными ссылками [[...]].
