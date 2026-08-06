---
id: ADR-100
title: KROFT Desktop control panel — system-at-a-glance Observability Dashboard
status: accepted
date: 2026-08-06
evidence_level: V
addresses:
  - TZ-RUN-01
  - KROFT-DESKTOP-v0.1
---

# ADR-100 — KROFT Desktop control panel

## Context

ТЗ-RUN-01 (ADR-099) поднял весь стек через `python composition/run_kroft.py`, но dashboard
(DESKTOP-01, ADR-097) показывал **пустые дефолты** (0 agents / 0 tasks / 0 models), потому что
реальные подсистемы не были подключены к snapshotter'у. Пользователь запросил **полноценную
панель управления** ("KROFT Desktop"), показывающую систему целиком: Kernel / Agents / Tasks /
Models / Marketplace / Federation / Memory / Trust / Logs — с живыми цифрами.

Стратегический поворот (2026-08-06): от «строим ядро ТЗ за ТЗ» к «делаем продукт, которым
пользуются ежедневно» (v0.1 release track).

## Decision

Расширить существующий `DashboardSnapshot` (frozen VO) НОВЫМИ ПОЛЯМИ (marketplace_skills,
federation_nodes, memory_notes, trust_score, logs) — **НЕ создавая новых портов**. Dashboard
остаётся duck-typed: `DashboardSnapshotter` принимает read-only провiders (callables);
`build_default_dashboard` (composition) подключает РЕАЛЬНЫЕ компоненты через их ПУБЛИЧНЫЕ аксессоры:

- Agents ← `IdentityRegistry.list()`
- Models ← `ModelRegistry.catalog()`
- Marketplace ← `SkillRepository._installed` (len)
- Federation ← `SkillDistributor._peers` (len)
- Memory notes ← `InMemoryGraphEngine.nodes()` (или layered semantic)
- Trust ← `ReferenceTrustRegistry.current_trust` (aggregate mean)
- Logs ← ring buffer (composition-level, НЕ kernel)

`run_kroft.py` создаёт и сидит demo-компоненты (6 agents, qwen3.5/llama3, 52 skills, 245 notes,
trust 0.97), подключая их к dashboard. Панель рендерится в формате KROFT Desktop (system-at-a-glance).

## Constraints honored

- **K5** — reuse existing components; NO new contract/port. DashboardSnapshotter knows only callables.
- **K6** — `services/desktop_dashboard.py` imports ONLY `contracts.i_dashboard` (duck-typed providers).
- **O1** — read-only; snapshotter writes nothing back to any kernel state.
- **I-09** — deterministic snapshot + stable JSON (`sort_keys`).
- **Флаг C** — dashboard NOT wired into build_kernel (opt-in surface).
- **Флаг 1b** — K8 tests separate (`tests/desktop/`).

## Consequences

- Панель показывает РЕАЛЬНОЕ состояние подсистем (не пустые дефолты).
- Tasks остаётся 0 (TaskStore отсутствует в коде — post-MVP daily-use pipeline подключит его).
- Demo-seed это composition-level scaffolding (НЕ ядро); реальная эксплуатация заменит seed на живые данные.

## Testing

- `tests/desktop/test_dashboard.py` (8 tests): snapshot reflects state, READ-ONLY, determinism,
  graceful missing components, panel aggregates wired, panel render layout, panel aggregates graceful.
- `tests/desktop/test_run_kroft.py` (8 tests): boot без LLM, mock LLM, dashboard renders, evolution
  progresses (v1→v2), graceful degradation, federation optional, panel live counts, federation nodes.
- KROFT_OS arch-gate: 14 positive + 6 negative (K1/K3/K6/K8 + F1–F6). akb-lint: 98→**99 ADR PASSED**.
