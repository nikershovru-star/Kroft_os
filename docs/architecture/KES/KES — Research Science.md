---
tags: [kroft, kes, research-science, evidence]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KES
summary: "Research Science (KES#1) — Evidence Level I–V, consensus, reproducibility. Прецедент: Evidence-Based SE."
---

# KES — Research Science

> Дисциплина KES: как KROFT оценивает КАЧЕСТВО исследований. Выведена из KP-002 (Evidence > Opinion).

## Метод — Evidence Level (I–V)
См. `akb/evidence_levels.yaml` (I=systematic review, II=empirical, III=comparative, IV=case, V=expert).
- Утверждение требует min Level III + consensus≥2 (KEH §3 gate).
- Level V (один блог) — только hypothesis, НЕ основание для ADR.

## Reproducibility
Источник воспроизводим: env + seed + data зафиксированы. Невоспроизводимое = не Evidence.

## ResearchArtifact (поля)
`evidence_level`, `confidence`, `source_quality`, `reproducibility`, `consensus`.

## Честная оценка
Прецедент Evidence-Based SE (Kitchenham SLR) доказал: hierarchy of evidence снижает bias.
KROFT применяет к инженерным решениям. Risk: бюрократия уровней — митигация: gate только
для ADR-уровня, не для каждой строки. LAW K8: данные в AKB, НЕ runtime.
