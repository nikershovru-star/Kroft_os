---
id: RFC-005
title: CI Pipeline & AKB Linter
status: decided
date: "2026-08-02"
previous_status: draft
decided_by: "TZ-003 WP-05 (human-approved scope)"
summary: >
  Ввести локальный CI-конвейер (scripts/ci.py) + AKB-линтер (tools/akb_lint.py)
  для автоматической проверки архитектурных инвариантов и валидности AKB
  перед коммитом.
relates_to: [ADR-031, ADR-022]
---

# RFC-005 — CI Pipeline & AKB Linter

## Problem

Архитектурный гейт (WP-02) доказателен, но запускается вручную. AKB не
валидируется. Дрейф «карта ≠ реальность» (TZ-002 WP-03) повторится без
автоматической проверки.

## Proposal

- `scripts/ci.py` — оркестратор (import-check, lint, tests, arch-gate,
  akb-lint, coverage).
- `tools/akb_lint.py` — валидатор AKB (YAML, ADR bijection, RFC, KL).
- pre-commit hook + dormant GitHub Actions workflow.

## Decision

**decided** (TZ-003 WP-05, human-approved). Реализован как ADR-031.

## Alternatives considered

- Внешний CI (GitLab/self-hosted) — отложен (нет remote, Q1 TZ-003).
- Только pre-commit без полного конвейера — недостаточно для CI-валидации
  волн (TZ-002 WP-12).
