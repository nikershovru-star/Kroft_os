---
tags: [kroft, keh, adr-handbook, decision, rfc]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KEH
summary: "ADR Handbook (KEH) — методика оценки ADR + RFC→ADR переход. Ссылается на KES Decision Science + RFC Layer."
---

# KEH — ADR Handbook

> Handbook KEH: как оценивать и принимать ADR. Выведен из KP-002/KP-007. Связан с RFC Layer.

## RFC → ADR конвейер
```
Research → Experiment → RFC (Draft→Review→Decided) → ADR → Implementation
```
Только **Decided** RFC становится ADR. Rejected RFC сохраняется (org memory: почему НЕ X).

## ADR как измеримый объект (KES Decision Science)
Каждый ADR несёт: `decision_score`, `confidence`, `risk`, `evidence`, `tradeoffs`, `revisit_trigger`.
Поля в `akb/adrs.yaml`. Пример: ADR-024 (score=88, confidence=0.82).

## Review правила
- ADR с confidence<0.5 → «proposed-low-confidence», revisit 3 мес (не 24).
- ADR без evidence (Level ≥ III) → возврат автору.
- ADR ссылается на RFC (`rfc: RFC-NNN` в adrs.yaml).

## Честная оценка
MS Well-Architected: «record confidence; low → reconsider». KROFT делает машинночитаемым.
RFC-слой (новый) устраняет «ADR как proposal» (gov.uk/Pragmatic Engineer). LAW K8: AKB docs/.
