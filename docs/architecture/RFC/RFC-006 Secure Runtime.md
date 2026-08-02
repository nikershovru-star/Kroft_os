---
id: RFC-006
title: Secure Runtime & Capability System
status: under_review
date: "2026-08-02"
previous_status: draft
summary: >
  Ввести capability-границу: агент получает только разрешённые возможности;
  авторизацию выполняет Kernel (не пользователь). Покрывает TZ-SEC-001 WP-01..WP-10:
  Capability Framework, RBAC, Policy Engine, Secret Manager, Secure Terminal,
  File Sandbox, Audit Log, Approval System, Security Tests, Docs.
relates_to: [ADR-032, ADR-033, ADR-034, ADR-028, ADR-029]
---

# RFC-006 — Secure Runtime & Capability System

## Problem

KROFT_OS сейчас = набор MCP-инструментов без авторизационной границы. Любой
агент имеет полный доступ ко всем инструментам (Filesystem, Shell, Git, Secrets,
Network). Нет разделения по ролям, нет маскировки секретов, нет audit-лога,
нет подтверждения опасных действий. Это блокирует переход к Multi-Agent
(TZ-MULTI-001) и Autonomous Platform (TZ-AGENT-001): без безопасности
оркестрация агентов = компрометация всей системы.

## Proposal

Ввести трёхслойную capability-архитектуру (детали в ADR-032/033/034):

1. **Ports** (`contracts/security/`): `ICapabilityManager`, `IPolicyEngine`,
   `ISecretManager`, `IAuditLogger`, `IApprovalManager`, `ITerminalExecutor`.
2. **Clean logic** (`kernel/security/`): `CapabilityManager`, `CapabilityContext`,
   `CapabilityPolicy`, `PolicyEngine` (wrapper), `ApprovalManager`, `Sandbox` policy.
   Зависит ТОЛЬКО от `contracts` (K1-compliant).
3. **IO impl** (`services/security/`): `SecretManager`, `AuditLogger`,
   `TerminalExecutor` — реализуют порты, тяжёлый IO вне kernel.

Существующий `services/policy_engine.py` (Wave 5: veto→filter→rank→fallback)
**расширяется** capability-veto (НЕ дублируется).

Поток вызова: `Tool.call → CapabilityManager.authorize(agent, tool) →
[PolicyEngine veto] → Execution`. Опасные действия → `ApprovalManager.wait()`.

## Decision

**under_review** (ожидает approval владельца архитектуры, K5). Реализация
блокируется до принятия ADR-032/033/034.

## Alternatives considered

- **Внешний IdP (OAuth2/JWT)** — отложен в TZ-MULTI-001 (tenant isolation нужен
  ДО authn). Здесь только порты + локальные роли.
- **OS-level sandbox (seccomp/cgroups)** — Linux-only; Windows = graceful
  degradation (job objects + path-prefix). Полный sandbox — отдельный WP.
- **Дублировать PolicyEngine** — rejected: нарушает DRY, конфликт с Wave 5.
