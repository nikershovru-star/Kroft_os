---
tags: [kroft, kes, reliability-science, chaos]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KES
summary: "Reliability Science (KES#7) — доказательство устойчивости через chaos. Прецедент: Netflix FIT / arxiv 2412.01416."
---

# KES — Reliability Science

> Дисциплина KES: тесты ≠ доказательство устойчивости. Выведена из KP-007 (Measurable).

## Resilience Proof (не unittest)
- `failure_injection`: искусственный сбой (kill process, net partition, latency)
- `chaos`: комбинированные сбои
- `recovery`: система восстанавливается (Supervisor, ADR-020/021)
- `mttr`: Mean Time To Recovery (метрика)
- `fault_isolation`: сбой НЕ каскадирует (bulkhead)

## Связь с KROFT
Supervisor уже даёт recovery (ProcessState FSM, QUARANTINED). Нужен chaos-harness
(ADR-021 A7) для доказательства. KROFT Phase 4 recovery — single sync (known-limitation,
см. org_memory.yaml) → кандидат на chaos-проверку.

## Честная оценка
Netflix FIT/Gremlin: Failure Injection + MTTR. KROFT применяет к Supervision Tree.
Risk: chaos в prod опасен — митигация: chaos в staging/controlled env. LAW K8: harness в
tests/, НЕ runtime.
