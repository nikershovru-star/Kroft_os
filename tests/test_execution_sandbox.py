"""Tests for TZ-EXECUTION-001 (Execution Sandbox, ADR-039).

Targets >=10 tests. Verifies SubprocessSandbox isolation + ToolRegistry
dangerous routing + fail-secure + K5 approval. Includes negative
proof-of-fire (K1 port, K8 adapter).
"""
from __future__ import annotations

import sys
import threading

import pytest

from contracts.i_execution_sandbox import IExecutionSandbox, ExecutionResult
from adapters.subprocess_sandbox import SubprocessSandbox
from services.tool_registry import ToolRegistry
from kernel.security.approval_manager import ApprovalManager


# --------------------------------------------------------------------------- #
# SubprocessSandbox
# --------------------------------------------------------------------------- #

def test_sandbox_echo_captures_stdout():
    sb = SubprocessSandbox()
    r = sb.execute([sys.executable, "-c", "print('hello')"])
    assert r.returncode == 0
    assert "hello" in r.stdout
    assert r.killed is False
    assert r.handle


def test_sandbox_nonzero_returncode():
    sb = SubprocessSandbox()
    r = sb.execute([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert r.returncode == 3
    assert r.killed is False


def test_sandbox_timeout_kills():
    sb = SubprocessSandbox()
    r = sb.execute([sys.executable, "-c", "import time; time.sleep(5)"], timeout_sec=0.3)
    assert r.killed is True
    assert r.returncode == -9


def test_sandbox_health():
    assert SubprocessSandbox().health() is True


def test_sandbox_thread_safety():
    sb = SubprocessSandbox()
    results = []
    def run():
        results.append(sb.execute([sys.executable, "-c", "print('ok')"]).returncode)
    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert results == [0] * 8


def test_sandbox_implement_port():
    assert isinstance(SubprocessSandbox(), IExecutionSandbox)


# --------------------------------------------------------------------------- #
# ToolRegistry dangerous routing
# --------------------------------------------------------------------------- #

def test_registry_safe_tool_runs_in_process():
    reg = ToolRegistry()  # no sandbox, safe tool -> zero regression
    reg.register("add", lambda a, b: a + b)
    assert reg.call("add", a=2, b=3) == 5


def test_registry_dangerous_without_sandbox_fail_secure():
    reg = ToolRegistry()  # no sandbox
    reg.register("rm", lambda: None, dangerous=True)
    with pytest.raises(RuntimeError):
        reg.call("rm")


def test_registry_dangerous_with_sandbox_runs():
    sb = SubprocessSandbox()
    reg = ToolRegistry(sandbox=sb)
    reg.register("echo", lambda: None, dangerous=True)
    r = reg.call("echo", command=[sys.executable, "-c", "print('sandboxed')"])
    assert isinstance(r, ExecutionResult)
    assert "sandboxed" in r.stdout


def test_registry_dangerous_approval_denied():
    sb = SubprocessSandbox()
    # ApprovalManager denies by default (no request approved) -> PermissionError
    reg = ToolRegistry(sandbox=sb, approval=ApprovalManager())
    reg.register("rm", lambda: None, dangerous=True)
    with pytest.raises(PermissionError):
        reg.call("rm", command=["false"])


# --------------------------------------------------------------------------- #
# Negative proof-of-fire (LAW)
# --------------------------------------------------------------------------- #

def test_k1_port_no_services_import():
    src = open("contracts/i_execution_sandbox.py", encoding="utf-8").read()
    assert "import services" not in src and "from services" not in src
    assert "import kernel" not in src and "from kernel" not in src


def test_k8_adapter_no_kernel_services_import():
    src = open("adapters/subprocess_sandbox.py", encoding="utf-8").read()
    assert "import kernel" not in src and "from kernel" not in src
    assert "import services" not in src and "from services" not in src
