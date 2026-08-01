---
tags: [kroft, kera, view, knowledge]
created: 2026-08-01
author: Hermes
status: v1.0
view_of: KERA
summary: "Knowledge View — где живут знания (AKB, Org Memory, Glossary, Research Archive)."
---

# KERA View — Knowledge

> KROFT-specific View (нет в классическом 4+1): где и как хранятся инженерные знания.
> Критично для KP-001 (Knowledge > Code) и L3/L17 зрелости.

## Источники знаний
- **AKB** (`docs/architecture/akb/`): laws/adrs/patterns/standards/tech_catalog/org_memory/
  evidence_levels/glossary/rfcs/history — machine-readable YAML.
- **Org Memory** (`org_memory.yaml`): почему + кто + ошибки + пересмотр (ADR-E, L17).
- **Glossary** (`glossary.yaml`): ubiquitous language (KL).
- **Research Archive** (`research/`): persist-выводы агентов (Artifact, KL-007).
- **Benchmarks/Experiments** (`benchmarks/`, `experiments/`): KES#2/#3 данные.

## Поток знаний
```
Research Mesh → AKB (write) → Synthesizer (RAG read) → ADR/RFC → Implementation
                                  ↑______________ Learning Loop ______________|
```
## Связь с KERA
- KERA §3 (EIP Learning Loop), §4 (Knowledge Platform P5). Здесь — структура знаний.
- LAW K8: AKB в docs/, НЕ импортируется runtime. Читается Hermes + tests/ (arch-gate).

## Честная оценка
Knowledge View — сердце KROFT (отличает от обычной ОС). AKB должен оставаться валидным
YAML (проверка при каждом PR). Stale AKB (catio: digital twin anti-pattern) хуже отсутствия.
