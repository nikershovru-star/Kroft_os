---
id: RFC-011
title: "Execution Sandbox — Isolated Tool Runtime for Agents"
status: under_review
date: "2026-08-02"
related: [TZ-EXECUTION-001, ADR-039, ADR-034, ADR-014, ADR-026, Stage-25, Stage-31]
authors: [kroft-architect]
evidence_level: III
---

# RFC-011: Execution Sandbox

## 1. Problem
Агенты и плагины сейчас выполняют произвольный код в процессе KROFT_OS:
- `DesktopAdapter.open_app()` — `os.system(start/open/xdg-open)` (adapters/desktop_adapter.py:78-82, Stage 31)
- `PluginLoader` — импортирует `.py` с полными правами процесса (Stage 25 limitation: "no sandbox")
- `healing.py` / `AgentOrchestrator` — вызывают lifecycle-переходы напрямую (ок, это internal)
- Потенциально: агент может сгенерировать и выполнить Python-код

Риски: один упавший/зависший tool убивает агента; злонамеренный плагин имеет
полный доступ к ФС/сети/памяти; `os.system` с user-input уязвим к injection.

## 2. Proposal

### 2.1 Порт `IExecutionSandbox` (`contracts/`)
```python
class IExecutionSandbox(ABC):
    @abstractmethod
    def execute(self, command: List[str], env: Optional[Dict[str,str]] = None,
                timeout_sec: Optional[float] = None, cwd: Optional[str] = None,
                label: str = "") -> ExecutionResult: ...
    @abstractmethod
    def kill(self, handle: str) -> bool: ...
    @abstractmethod
    def health(self) -> bool: ...
```
`ExecutionResult` — frozen dataclass: returncode, stdout, stderr, handle,
duration_ms, killed.

### 2.2 Адаптер SubprocessSandbox (`adapters/`, default)
`subprocess.run(capture_output=True, timeout=timeout_sec, cwd=cwd)`.
Thread-safe (threading.Lock), UUID-handles, Popen.terminate() → kill().
Cross-platform: Windows (creationflags при необходимости) + POSIX.
Zero external deps (stdlib only).

### 2.3 Интеграция
| Точка | Что меняется |
|-------|-------------|
| `contracts/agent.py::Tool` | добавить поле `dangerous: bool = False` |
| `ToolRegistry` | принимает `sandbox: Optional[IExecutionSandbox]`. Инструменты помечаются `dangerous` при регистрации. `dangerous=True` + `sandbox=None` → `RuntimeError` (fail-secure). `dangerous=True` + sandbox есть → маршрутизируется через `sandbox.execute()` |
| `DesktopAdapter.open_app` | вместо `os.system` вызывает `sandbox.execute([cmd, arg])` (если sandbox wired) |
| `PluginLoader` | (Future) Plugin code execution через sandbox вместо `importlib.util` в основном процессе |
| `AgentService.dry_run` | показывает, какая команда пойдёт в sandbox; реальное выполнение — только через sandbox для dangerous tools |

### 2.4 Security Model
- **Timeout**: все sandbox-вызовы с `timeout_sec` (default 30s). Превышение → `killed=True`, returncode -9.
- **Approval Gate (K5, ADR-034)**: инструменты с `dangerous=True` требуют `ApprovalManager.request()` перед `sandbox.execute()`. `ToolRegistry` проверяет approval status.
- **Env/CWD isolation**: sandbox запускается с `cwd=vault_path`, env без `OPENAI_API_KEY` и других sensitive vars (фильтрация через deny-list).

## 3. LAW Compliance
- **K1**: порт в `contracts/` (stdlib only).
- **K3**: `SubprocessSandbox` создаётся в `composition/`.
- **K5**: dangerous tool → approval перед execute.
- **K6**: `services/` → `adapters/` только через `IExecutionSandbox`.
- **K8**: sandbox-логика в `adapters/` (infra), не в `kernel/`/`runtime/`.

## 4. Risks
- **PyAutoGUI не sandboxable**: click/type/screenshot требуют GUI-access в основном процессе. Честное ограничение: GUI-автоматизация остаётся in-process, sandbox покрывает только shell/Python execution.
- **Plugin registration через sandbox**: плагин, запущенный в subprocess, не может зарегистрировать команды в родительском argparse. Решение: two-phase load — (1) sandboxed AST-scan + validation, (2) in-process registration только после проверки. Вне скоупа TZ-EXECUTION-001.
- **Overhead**: subprocess на каждый tool call ~50-100ms. Acceptable для dangerous/slow операций (open_app, export, plugin init).

## 5. Alternatives Considered
- **DockerSandbox** — отложено: требует Docker daemon, не кросс-платформенно, external dependency. `SubprocessSandbox` покрывает 80% рисков stdlib-only.
- **In-process RestrictedPython** — отложено: сложно, не даёт изоляции памяти/CPU, external dep.

## 6. Validation (цель при K5 «go»)
- Тесты `SubprocessSandbox`: echo, timeout/kill, returncode, stdout/stderr capture, thread-safety.
- Тесты `ToolRegistry`: dangerous tool без sandbox → RuntimeError; dangerous tool с sandbox → subprocess executed; safe tool → zero regression (in-process).
- Arch-gate: K1 (contracts clean), K6 (services→adapters через порт).
- Suite target: +10 tests, ≥914 passed.
