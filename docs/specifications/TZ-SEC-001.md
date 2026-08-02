---
id: TZ-SEC-001
title: KROFT_OS Secure Runtime & Capability System
status: Design
priority: Critical
depends_on: TZ-003 (Completed)
lang: ru
date: 2026-08-02
---

# TZ-SEC-001 — Secure Runtime & Capability System

## Цель
Превратить KROFT_OS из набора MCP-инструментов в безопасную агентную платформу.
После выполнения каждый агент получает только разрешённые возможности.
Не пользователь доверяет агенту — агенту доверяет Kernel.

## WP-01 — Capability Framework
Система разрешений: `Tool.call` → `CapabilityManager → Authorization → Tool Execution`.
Интерфейсы: `ICapabilityManager`, `ICapabilityPolicy`, `ICapabilityContext`.
Capability-категории: Tool, Filesystem, Network, Memory, RAG, Graph, Planner, Shell,
Python, Git, Secrets, Admin.
Каждый Tool обязан иметь `required_capabilities`
(напр. `vault_create` requires `Filesystem.Write` + `Memory.Store`).

## WP-02 — Role Based Access
Роли: Architect, Researcher, Coder, Analyst, Reviewer, MemoryAgent, Planner, Operator, Admin.
Каждая роль → permissions. Пример: Architect → {Planner, Memory, Graph}, NO {Shell, Git, Secrets}.
Operator → {Shell, Filesystem, Git}.

## WP-03 — Policy Engine
`PolicyEngine`: Agent → Role → Capability → Tool → Execution.
Пример: Planner вызывает `terminal.run()` → DENY.

## WP-04 — Secret Manager
`SecretManager` (services/security): OpenAI, OpenRouter, GitHub, Anthropic, Gemini,
DeepSeek, Telegram, Discord, SMTP, SSH, Git.
ЗАПРЕТ: `print(api_key)`, `log(api_key)`, `memory.store(api_key)`, `vault.save(api_key)`.
Все секреты маскируются автоматически.

## WP-05 — Secure Terminal
`TerminalExecutor`: blacklist `rm -rf`, `shutdown`, `format`, `diskpart`, `reg delete`,
`del /f /s`, `taskkill *`, `sudo`, `powershell download`, `curl | bash`.
Whitelist + Blacklist + Timeout + Sandbox.

## WP-06 — File Sandbox
Разрешено: Obsidian Vault, Workspace, Temp, Projects.
Запрещено (без подтверждения): Windows, Program Files, AppData, Users, Registry.

## WP-07 — Audit Log
Каждый вызов (Tool/Memory/Shell/Git/Filesystem) логируется:
timestamp, agent, tool, arguments, result, duration, status.

## WP-08 — Approval System
Опасные действия → `WAIT_APPROVAL`: Delete Folder, Git Push, Git Commit,
Execute Python, Shell, Secrets, Filesystem Delete.

## WP-09 — Security Tests
Покрытие Capabilities/Policies/Secrets/Sandbox/Audit/Approval ≥ 95%.

## WP-10 — Documentation
ADR-032 Security Architecture, ADR-033 Capability Model, ADR-034 Approval Workflow.

## Итог (новые модули)
```
kernel/security/
  capability_manager.py  capability_context.py  capability_policy.py
  policy_engine.py  approval_manager.py  audit_logger.py
  secret_manager.py  sandbox.py  terminal_executor.py
```
Новые порты: `ICapabilityManager`, `IPolicyEngine`, `ISecretManager`,
`IAuditLogger`, `IApprovalManager`, `ITerminalExecutor`.
Новые тесты: `tests/security/`.
Новые ADR: ADR-032, ADR-033, ADR-034.

## После TZ-SEC-001 (критический путь)
→ TZ-MULTI-001 (Multi-Agent) → TZ-KNOW-001 (Knowledge v3) → TZ-AGENT-001 (Autonomous Platform).
Порядок: сначала безопасность/контроль, затем оркестрация, затем знания, затем автономность.

## Заметки исполнителя (2026-08-02, pre-start)
- Baseline re-verify: `kernel/` содержит ТОЛЬКО `kernel.py` + `__init__.py`
  (подслоя `security/` НЕТ). `services/policy_engine.py` УЖЕ существует (Wave 5:
  veto→filter→rank→fallback pipeline) — WP-03 интегрирует capability-проверку в него,
  не дублирует. `services/agent_platform.py`, `services/simple_guardrail.py` — есть.
- K1-ограничение: `kernel/security/*` НЕ может импортировать `services/` (иначе K1).
  Значит тяжёлые IO-сервисы (SecretManager, AuditLogger, TerminalExecutor) → реализации
  в `services/security/` через порты `contracts/security/`; чистая логика
  (CapabilityManager, PolicyEngine wrapper, ApprovalManager, Sandbox policy) → в `kernel/security/`
  (зависит только от contracts). Требует ADR (K5 + RFC обязателен для крупных изменений).
