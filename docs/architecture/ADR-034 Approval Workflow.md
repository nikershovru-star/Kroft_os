---
id: ADR-034
title: Approval Workflow (Human-in-loop for Dangerous Actions)
status: proposed
date: "2026-08-02"
decision_score: 0.9
confidence: high
risk: low
evidence_level: III
evidence:
  - "TZ-SEC-001 WP-08: Approval System (WAIT_APPROVAL для опасных действий)"
  - "LAW K5: deploy / изменение законов / self-improve — только с подтверждения человека"
relates_to: [ADR-032, ADR-033, RFC-006]
laws_affected: [K5]
---

# ADR-034 — Approval Workflow (Human-in-loop)

## Context

Некоторые действия необратимы или опасны (удаление, push, выполнение кода).
Без подтверждения агент может скомпрометировать систему (K5: human approval
обязательно для опасных действий).

## Decision

**IApprovalManager** в `contracts/security/` + реализация в `kernel/security/`
(чистая логика gate) + `services/security/` (если нужен UI/notify).

**Dangerous actions → `WAIT_APPROVAL`** (Kernel блокирует до решения):
- Delete Folder / Filesystem Delete
- Git Push / Git Commit
- Execute Python
- Shell (вне whitelist)
- Secrets (чтение/запись)
- Kernel reconfigure

Поток:
```
Tool.call(dangerous)
  → ApprovalManager.request(agent, action, args)
  → Kernel state: WAIT_APPROVAL
  → [human approves / denies]
  → Execution | DENY
```

Approval НЕ блокирует ядро (async queue); другие агенты продолжают работу.

## Consequences

**Positive:** K5 соблюдён (human-in-loop для опасного), необратимые действия
защищены, audit-лог фиксирует решение.

**Negative:** latency на опасных действиях (приемлемо по K5).

## Status

**proposed** — ожидает approval (K5).

## Evidence Level: III
- Decision_score: 0.9, Confidence: high, Risk: low.
