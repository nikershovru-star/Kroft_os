---
id: ADR-031
title: CI Pipeline & AKB Linter
status: proposed
date: "2026-08-02"
decision_score: 0.9
confidence: high
risk: low
evidence_level: III
evidence:
  - "TZ-003 WP-05: без CI любое изменение требует ручного прогона 768 тестов + гейта (friction -> пропуск проверок)"
  - "WP-02 (TZ-001): arch-gate расширен до 8 positive + 6 negative, но без CI он не запускается автоматически"
  - "PROJECT_STATUS.md v1.0: 768 passed / 0 failed / 0 open violations (baseline для CI)"
relates_to: [ADR-022, ADR-028, ADR-029]
laws_affected: [K5, K7, K8]
---

# ADR-031 — CI Pipeline & AKB Linter

## Context

После WP-02 (TZ-001) Architecture Gate стал доказательным (8 positive + 6
negative тестов), но он запускается только вручную. Без автоматического
конвейера любое изменение требует ручного прогона 768 тестов + гейта — это
friction, который ведёт к пропуску проверок и дрейфу архитектуры (та же
проблема, что породила TZ-002 WP-03).

AKB (Architecture Knowledge Base) — машиночитаемый источник истины для
законов/ADR/паттернов, но его валидность никем не проверяется. Расхождение
`adrs.yaml` ↔ `ADR-*.md` остаётся незамеченным.

## Decision

Ввести локальный CI-конвейер `scripts/ci.py` с явными стадиями:

| Стадия | Блокирующая | Инструмент |
|--------|-------------|-----------|
| import-check | да | `import kernel, runtime, ...` |
| lint (ruff) | нет | `ruff check` (опционален) |
| tests | да | `pytest tests/` |
| arch-gate | да | `pytest test_architecture*.py` |
| akb-lint | да | `tools/akb_lint.py` |
| coverage | нет | `pytest --cov` |

Плюс `tools/akb_lint.py` — валидатор AKB (YAML-парсинг, ADR bijection,
RFC-переходы, KL-синонимы, evidence_level). Pre-commit hook
(`.pre-commit-config.yaml` + `scripts/precommit.py`) запускает быстрый
поднабор (lint + arch-gate + akb-lint). Dormant `.github/workflows/ci.yml`
активируется при появлении remote.

## Consequences

**Positive:**
- Архитектурные инварианты проверяются до коммита (не post-hoc).
- AKB валиден и синхронизирован с `ADR-*.md` (блокирующая проверка bijection).
- Время полного прогона ≤ 35s (факт), быстрого ≤ 2s.

**Negative / Risks:**
- ruff не установлен в среде → lint non-blocking (R1: не ломает workflow).
- evidence_level пока non-blocking (WARN) до WP-08 (TZ-002 Wave 2) — F6
  станет блокирующим после закрытия.

## Status

**proposed** — реализован в WP-05 (TZ-003), ожидает одобрения человека (K5).
Перевод в accepted требует подтверждения владельца архитектуры.

## Evidence Level: III
- Decision_score: 0.9, Confidence: high, Risk: low.
- Источники: TZ-003 WP-05, WP-02 результаты, PROJECT_STATUS.md baseline.
