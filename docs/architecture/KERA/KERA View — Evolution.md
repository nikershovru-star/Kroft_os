---
tags: [kroft, kera, view, evolution, maturity]
created: 2026-08-01
author: Hermes
status: v1.0
view_of: KERA
summary: "Evolution View — как KROFT меняется (maturity L1–L18, Meta Engine, continuous-*)."
---

# KERA View — Evolution

> KROFT-specific View: траектория изменений системы. Связан с L1–L18 (ADR-023/024) и
> Evolution Platform (P10). Именованные этапы зрелости ВМЕСТО жёсткой нумерации L1–L18
> как primary names (по principal-review).

## Модель зрелости (named stages, не просто L1–L18)
| Этап (primary name) | Внутренний код | Суть |
|---|---|---|
| **Foundation** | L1–L3 | Intelligence, Reviewer, Knowledge Base (AKB) ✅ |
| **Operational** | L4–L10 | Pattern Lib, Simulator, TD, Evolution, Autonomous, Benchmark, AI Chief Architect |
| **Autonomous** | L11–L18 | Meta Engine, Governance, Continuous Research, Forecasting, Experiment, Self-Improving, Org Memory, Autonomous CTO |

Преимущество: можно вставить промежуточный stage (напр. «Operational+») БЕЗ переименования
всей шкалы. Коды L* — внутренние, в доках — смысловые названия.

## Механизмы эволюции
- **Meta Architecture Engine** (L11): анализ устаревших LAW/ADR/интерфейсов → propose (НЕ apply).
- **Continuous Research/Refactor/Learning/Benchmark/Governance** (P10): EIP-контуры.
- **AKB history.yaml**: Knowledge Base Update на каждое изменение (traceability).

## Связь с KERA
- KERA §4 (Platforms P10), §5 (зрелость). Здесь — динамика зрелости.
- LAW меняется только через meta-ADR (KEH §6), выведен из KP (KP → LAW traceability).

## Честная оценка
Evolution View устраняет твоё замечание про P/L-нумерацию: коды остаются (внутренние),
primary names — смысловые (Research Platform, Foundation stage...). Шкала расширяема.
KROFT уже на Foundation (L1/L3 ✅); Operational/Autonomous — roadmap.
