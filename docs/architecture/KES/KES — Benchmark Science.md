---
tags: [kroft, kes, benchmark-science, reproducible]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KES
summary: "Benchmark Science (KES#2) — воспроизводимый benchmark. Прецедент: SPEC RG / Henning."
---

# KES — Benchmark Science

> Дисциплина KES: как делать ВОСПРОИЗВОДИМЫЕ benchmark'и. Выведена из KP-007 (Measurable).

## Reproducible Benchmark Protocol
- Fixed env (lockfile, OS version pinned)
- Warmup N итераций перед замером
- Seed зафиксирован
- Variance report (mean ± std, p95, min/max)
- Результат повторим через год (version-pinned)

## Метрики (Scheduler A vs B)
`CPU | RAM | Latency | Recovery(MTTR) | Scalability | Energy | Cost`

## Хранение
`akb/benchmarks/<topic>.yaml`: env_hash, seed, metrics, timestamp → trend виден исторически.

## Честная оценка
SPEC RG/Henning: «large variability → controlled measurements, warmup, variance». Невоспроиз-
водимый benchmark («быстрее!» без variance) = не Evidence (KES#1 Level V). LAW K8: данные в AKB.
