---
id: ADR-033
title: Capability Model (RBAC + Tool Requirements)
status: proposed
date: "2026-08-02"
decision_score: 0.9
confidence: high
risk: low
evidence_level: III
evidence:
  - "TZ-SEC-001 WP-01/WP-02: Capability Framework + Role Based Access"
  - "services/agent_platform.py уже имеет AgentResult/agent-модель (точка интеграции)"
relates_to: [ADR-032, ADR-034, RFC-006]
laws_affected: [K1, K5, K6]
---

# ADR-033 — Capability Model (RBAC + Tool Requirements)

## Context

Инструменты вызываются напрямую (`tool.call(...)`) без декларации требуемых
прав. Нет ролей. Нужна модель: каждый Tool декларирует `required_capabilities`,
каждая роль — набор разрешённых capability.

## Decision

**Capability-категории** (с суб-операциями Read/Write/Execute где применимо):

`Tool`, `Filesystem`, `Network`, `Memory`, `RAG`, `Graph`, `Planner`,
`Shell`, `Python`, `Git`, `Secrets`, `Admin`.

**Roles** (RBAC): `Architect`, `Researcher`, `Coder`, `Analyst`, `Reviewer`,
`MemoryAgent`, `Planner`, `Operator`, `Admin`.

Примеры mapping:
- `Architect` → {Planner, Memory, Graph}; NO {Shell, Git, Secrets}.
- `Operator` → {Shell, Filesystem, Git}.
- `Admin` → все.

**Tool declaration** (контракт):
```python
@tool(required_capabilities=["Filesystem.Write", "Memory.Store"])
def vault_create(...) -> ...
```

**ICapabilityManager.authorize(agent, tool) → Allow | Deny**:
Agent → Role → Permissions → Tool.required_capabilities → PolicyEngine veto → result.

Интеграция: `services/agent_platform.py` передаёт агента в `CapabilityManager`
до выполнения tool. Существующий `PolicyEngine` (Wave 5) получает capability-veto
hook.

## Consequences

**Positive:** декларативность (tool сам объявляет права), централизованная
проверка, лёгкое тестирование (negative test: Planner → terminal.run → DENY).

**Negative:** каждый новый tool обязан объявлять `required_capabilities`
(дисциплина; ловится arch-gate).

## Status

**proposed** — ожидает approval (K5).

## Evidence Level: III
- Decision_score: 0.9, Confidence: high, Risk: low.
