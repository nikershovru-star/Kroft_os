---
tags: [kroft, kes, decision-science, adr-scoring]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KES
summary: "Decision Science (KES#4) — ADR становится измеримым (score/confidence/risk/evidence). Прецедент: MS Well-Architected."
---

# KES — Decision Science

> Дисциплина KES: как измерять решения. Выведена из KP-002 (Evidence > Opinion) + KP-007 (Measurable).

## ADR как измеримый объект
Каждый ADR в `akb/adrs.yaml` несёт (KES#4):
- `decision_score` (0–100, weighted по characteristics)
- `confidence` (0.0–1.0, из Evidence Level источников)
- `risk` (low/med/high + mitigation)
- `evidence` (ссылки на ResearchArtifact с evidence_level)
- `tradeoffs` (что отдали)
- `revisit_trigger` (условие пересмотра)

## Правило
ADR с confidence<0.5 → «proposed-low-confidence», revisit через 3 мес (не 24).
Пример: ADR-024 имеет decision_score=88, confidence=0.82 (уже в AKB).

## Честная оценка
MS Well-Architected/Fowler: «record confidence; low → future reconsideration». KROFT делает
это машинночитаемым (YAML). Risk: score субъективен — митигация: score выводится из
объективных полей (evidence_level × consensus), не «на глаз».
