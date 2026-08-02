---
id: ADR-032
title: Security Architecture (Capability Boundary)
status: accepted
evidence_level: III
date: "2026-08-02"
decision_score: 0.92
confidence: high
risk: low
evidence:
  - "TZ-SEC-001 (Design, Critical): требование capability-границы перед Multi-Agent/Autonomous"
  - "kernel/ содержит ТОЛЬКО kernel.py + __init__.py (baseline re-verify 2026-08-02)"
  - "services/policy_engine.py уже существует (Wave 5) — интеграция, не дубль"
  - "LAW K1: kernel НЕ импортирует services/adapters/infrastructure"
relates_to: [ADR-028, ADR-029, ADR-033, ADR-034, RFC-006]
laws_affected: [K1, K3, K5, K8]
---

# ADR-032 — Security Architecture (Capability Boundary)

## Context

KROFT_OS — набор MCP-инструментов без авторизационной границы. Любой агент
имеет полный доступ к Filesystem/Shell/Git/Secrets. Это блокирует Multi-Agent
(TZ-MULTI-001) и Autonomous Platform (TZ-AGENT-001): без безопасности
оркестрация = компрометация.

Kernel должен авторизовать агента (не пользователь доверяет агенту — агенту
доверяет Kernel).

## Decision

Трёхслойная capability-архитектура, K1-compliant:

| Слой | Путь | Зависимости | Назначение |
|------|------|-------------|-----------|
| **Ports** | `contracts/security/` | — | `ICapabilityManager`, `IPolicyEngine`, `ISecretManager`, `IAuditLogger`, `IApprovalManager`, `ITerminalExecutor` |
| **Clean logic** | `kernel/security/` | `contracts` (ТОЛЬКО) | `CapabilityManager`, `CapabilityContext`, `CapabilityPolicy`, `PolicyEngine` (wrapper), `ApprovalManager`, `Sandbox` policy |
| **IO impl** | `services/security/` | `contracts`, `services` | `SecretManager`, `AuditLogger`, `TerminalExecutor` |

**Критично для K1:** `kernel/security/*` НЕ импортирует `services/`, `adapters/`,
`infrastructure/`. Чистая логика (capability-check, policy-veto, approval-gate,
sandbox-policy) живёт в kernel; тяжёлый IO (секреты, лог, терминал) — в
`services/security/` через порты.

Существующий `services/policy_engine.py` (Wave 5) **расширяется** capability-veto
(НЕ создаётся второй PolicyEngine).

## Consequences

**Positive:**
- Capability-граница: агент получает только разрешённое (RBAC + policy).
- K1/K3/K8 соблюдены: kernel/security чист (contracts-only).
- Audit + Approval = подотчётность + human-in-loop (K5).
- Testable: capability/policy/sandbox — чистые, мокаются через порты.

**Negative / Risks:**
- Дополнительный слой (но маленький, contract-only).
- Сложность тестирования sandbox на Windows (graceful degradation).
- Маскировка секретов требует pre-commit + akb-lint regex (`password=`, `token=`).

## Status

**proposed** — ожидает approval (K5). Реализация блокируется до принятия.

## Evidence Level: III
- Decision_score: 0.92, Confidence: high, Risk: low.
- Источники: TZ-SEC-001, baseline re-verify, LAW K1.
