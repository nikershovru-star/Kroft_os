---
tags: [kroft, keh, benchmark-handbook, reproducible]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KEH
summary: "Benchmark Handbook (KEH) — требования к воспроизводимым бенчмаркам. Ссылается на KES Benchmark Science."
---

# KEH — Benchmark Handbook

> Handbook KEH: как делать бенчмарки. Выведен из KP-007 (Measurable). Связан с KES Benchmark Science.

## Требования (Reproducible Benchmark)
- Fixed env (lockfile, OS version pinned)
- Warmup N итераций
- Seed зафиксирован
- Variance report (mean ± std, p95)
- Результат повторим через год (version-pinned)

## Метрики
`CPU | RAM | Latency | Recovery(MTTR) | Scalability | Energy | Cost`

## Хранение
`akb/benchmarks/<topic>.yaml`: env_hash, seed, metrics, timestamp → trend.

## Запрещено
«Быстрее!» без variance report и fixed env = не Evidence (KES Level V).

## Честная оценка
SPEC RG/Henning: «large variability → controlled measurements». KROFT применяет строго.
Risk: overhead на малых бенчмарках — митигация: требования для значимых сравнений (Schedule A vs B),
не для микро-замеров. LAW K8: данные в AKB, НЕ runtime.
