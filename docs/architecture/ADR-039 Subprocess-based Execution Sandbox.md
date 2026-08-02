---
id: ADR-039
title: "Subprocess-based Execution Sandbox (IExecutionSandbox)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.85
confidence: high
risk: medium
related: [TZ-EXECUTION-001, RFC-011, ADR-034, ADR-026, Stage-25, Stage-31]
---

# ADR-039: Subprocess-based Execution Sandbox

## 1. Context
После TZ-AGENT-001 и WP-10 KROFT_OS имеет оркестрацию агентов и supervisor
recovery. Но агенты выполняют инструменты в основном процессе:
`os.system` (adapters/desktop_adapter.py:78), `importlib.util` для плагинов,
PyAutoGUI. Это нарушает принцип изоляции (Stage 25/31 honest limitations:
"no sandbox").

Без sandbox:
- Плагин с `__import__('os').system('rm -rf /')` уничтожает vault.
- `open_app` с user-controlled filename → shell injection (подтверждено:
  `os.system(f'start "" "{name}"')` не экранирует `name`).
- Бесконечный цикл в tool callable → блокирует агента навсегда (нет timeout).

## 2. Decision
Ввести порт `IExecutionSandbox` (`contracts/`) и реализацию `SubprocessSandbox`
(`adapters/`, stdlib `subprocess`):
- **Default**: `SubprocessSandbox` wired в DI для всех dangerous tools.
- **Zero regression**: `ToolRegistry(..., sandbox=None)` — поведение Stage 33
  (in-process) сохраняется.
- **Dangerous gate**: `ToolRegistry` флаг `dangerous=True` + `sandbox=None` →
  `RuntimeError` (fail-secure, не silent).
- **K5 integration**: `ApprovalManager.request()` перед execute dangerous tool
  (ADR-034).
- **Integration points** (fact-checked 2026-08-02):
  - `contracts/agent.py::Tool` — добавить `dangerous: bool = False`.
  - `services/tool_registry.py::ToolRegistry` — `sandbox` параметр + routing.
  - `adapters/desktop_adapter.py::DesktopAdapter.open_app` — `os.system` →
    `sandbox.execute([...])`. (НЕ `services/desktop_service.py` — он лишь
    делегирует через `IDesktop`; реальный `os.system` в adapter.)

## 3. Consequences
**Positive:**
- Shell-injection устранён (command как `List[str]`, не строка).
- Timeout + kill для зависших операций.
- Плагиновый код можно валидировать в sandbox перед in-process регистрацией (future).
- Production-ready: агент не падает из-за buggy tool.

**Negative:**
- PyAutoGUI (click/type) остаётся in-process — нельзя sandbox GUI automation.
- Subprocess overhead ~50ms per call.
- Plugin registration (Phase 2) всё ещё требует in-process import для argparse wiring.

## 4. Validation
- Тесты `SubprocessSandbox`: echo, timeout/kill, returncode, stdout/stderr capture, thread-safety.
- Тесты `ToolRegistry`: dangerous tool без sandbox → RuntimeError; dangerous tool с sandbox → subprocess executed; safe tool → zero regression (in-process).
- Arch-gate: K1 (contracts clean), K6 (services→adapters через порт).
- Suite target: +10 tests, ≥914 passed.

## 5. References
- RFC-011
- Stage 25 HONEST LIMITATIONS (Plugin System — no sandbox)
- Stage 31 HONEST LIMITATIONS (Desktop Automation — no sandbox)
- `kernel/security/sandbox.py` — `FileSandbox` (path guard, TZ-SEC-001 WP-06) —
  НЕ конфликтует: это process/command sandbox, не file sandbox.
