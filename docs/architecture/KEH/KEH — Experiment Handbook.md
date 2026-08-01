---
tags: [kroft, keh, experiment-handbook, scientific-method]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KEH
summary: "Experiment Handbook (KEH) — правила экспериментов (Hypothesis→Metrics→Result). Ссылается на KES Benchmark Science."
---

# KEH — Experiment Handbook

> Handbook KEH: как ставить эксперименты. Выведен из KP-007 (Measurable). Связан с KES Benchmark Science.

## Experiment Record (в AKB `experiments/`)
```
Hypothesis → Experiment → Metrics → Result → Conclusion
```
- Hypothesis должна быть falsifiable (проверяема).
- Control vs Treatment зафиксированы.
- Metrics из Benchmark Science (CPU/RAM/Latency/Recovery/...).
- Result: принято/отвергнуто по threshold (не «почувствовалось»).
- Conclusion → AKB (Learning Loop).

## Запрещено
Изменение без ExperimentRecord для значимых решений (L15 Experiment Engine).

## Честная оценка
Scientific method: A/B как controlled experiment. KROFT применяет к архитектурным изменениям.
Risk: overhead на малых изменениях — митигация: Experiment только для значимых (затрагивающих
LAW/слой/платформу), не для bugfix. LAW K8: данные в AKB, НЕ runtime.
