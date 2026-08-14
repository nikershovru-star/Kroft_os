---
tags: [kroft-os, retrieval, representation-gate, evaluation]
created: 2026-08-10
status: CLOSED — KEEP B
---

# REPRESENTATION QUALITY GATE — Embedding Variant A/B/C/D

**Дата:** 2026-08-10
**Решение:** **KEEP B** (production patch НЕ требуется; full re-embed НЕ оправдан)

## STEP 1 — IMMUTABLE BASELINE (production, read-only)
```
nodes      = 16792
edges      = 33490
vectors    = 16746
index_terms= 190956
size_bytes = 745324974
sha256     = f58a30b3ece399366c7f051db00035f0e7af3fd3e4ecf756653e207cb8acdc0e
```
Production snapshot НЕ изменялся. 16746 vectors НЕ перегенерировались.

## STEP 2/4 — SAMPLE (read-only eval, in-memory embeddings)
- 23 источника, 885 chunks (≤40/src).
- Типы: entity-heavy (Shannon, Newell+Simon, Wiener, Goodfellow, Pearl),
  conceptual (Polya, Sutton, Murphy, Bishop), technical (AIMA, Szeliski,
  Kleppmann, Åström/Murray), humanities/OCR (Aristotle, Bacon, Descartes, Hume),
  RAG (Bratanić).
- A/B/C/D эмбеджены IN-MEMORY (bge-m3, 3540 vectors, 706s). Ничего НЕ записано в prod.

## Variants
- A = answer
- B = question + answer + related_concepts  ← **CURRENT PRODUCTION**
- C = title + question + answer + related_concepts
- D = title + author + question + answer + tags + related_concepts

## STEP 5 — RESULTS (hybrid RRF k=60 rank; macro over entity/concept/title/author/cross)

| var | R@5  | R@10 | MRR  | entity | conceptual | title | author | cross | neg.top1cos↓ |
|-----|------|------|------|--------|------------|-------|-------|-------|--------------|
| A   | 0.91 | 0.96 | 0.86 | 0.83   | 0.80       | 1.00  | 1.00  | 1.00  | 0.429        |
| B   | 0.96 | 0.96 | 0.86 | 1.00   | 0.80       | 1.00  | 1.00  | 1.00  | 0.432        |
| C   | 0.96 | 1.00 | 0.84 | 1.00   | 1.00       | 1.00  | 1.00  | 1.00  | 0.425        |
| D   | 0.96 | 1.00 | 0.87 | 1.00   | 1.00       | 1.00  | 1.00  | 1.00  | 0.421        |

(negative: lower top1 cosine = less false confidence = better)

## STEP 6 — DECISION RULE
1. C/D улучшает aggregate R@5? **НЕТ** — B=C=D=0.96 (Δ=0.00).
2. Не ухудшает conceptual? **ДА** — R@5 равно (0.80), R@10 улучшено (0.80→1.00).
3. Не ухудшает negative? **ДА** — top1cos C/D ниже B (0.425/0.421 < 0.432).
4. Улучшение на нескольких источниках, не только Shannon? **ДА** — entity
   (Newell/Simon/Wiener/Goodfellow/Pearl), conceptual (Polya/Sutton/Murphy),
   title/author/cross — все на разных источниках.
5. **Практически существенно? НЕТ** — R@5 идентичен; R@10 +0.04 на 23-источниковой
   выборке; MRR в пределах шума (0.84–0.87). Правило 5: «+0.01 на нескольких
   запросах → KEEP B».

C vs D: равны по entity (оба 1.00), D чуть выше MRR (0.87 vs 0.84, шум). C проще
(меньше метаданных) и не хуже по балансу → если бы патчили, выбрали бы C, но
патч не оправдан.

## STEP 7 — VERDICT
**KEEP B.**
Изменение на C/D даёт выигрыш в пределах погрешности (R@5 идентичен, R@10 +0.04).
Переключение потребовало бы full re-embed 16746 vectors (destructive, запрещено
ТЗ) ради несущественного прироста. B — достаточно хорош и не требует перестройки.

Production patch и full re-embed — отдельной командой (НЕ выполнялись).
