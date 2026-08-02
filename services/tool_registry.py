"""ToolRegistry — register and invoke tools (Stage 33 + TZ-EXECUTION-001).

K1-compliant: contracts only + stdlib. Dangerous tools are routed through an
injected IExecutionSandbox (ADR-039); a dangerous tool with no sandbox raises
fail-secure (RuntimeError). Dangerous execution requires K5 approval
(ApprovalManager, ADR-034).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from contracts import Tool
from contracts.i_execution_sandbox import IExecutionSandbox
from contracts.security import IApprovalManager


class ToolRegistry:
    def __init__(
        self,
        sandbox: Optional[IExecutionSandbox] = None,
        approval: Optional[IApprovalManager] = None,
    ) -> None:
        self._tools: Dict[str, Tool] = {}
        self._sandbox = sandbox
        self._approval = approval

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        description: str = "",
        dangerous: bool = False,
        required_capabilities: Optional[List[str]] = None,
    ) -> None:
        self._tools[name] = Tool(
            name=name,
            fn=fn,
            description=description,
            required_capabilities=required_capabilities or [],
            dangerous=dangerous,
        )

    def call(self, tool_name: str, **kwargs: Any) -> Any:
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' not registered")
        tool = self._tools[tool_name]
        if tool.dangerous:
            return self._call_dangerous(tool, **kwargs)
        return tool.fn(**kwargs)

    def _call_dangerous(self, tool: Tool, **kwargs: Any) -> Any:
        if self._sandbox is None:
            # Fail-secure: never run a dangerous tool without isolation.
            raise RuntimeError(
                f"dangerous tool '{tool.name}' registered but no IExecutionSandbox wired"
            )
        # K5: require human approval before executing a dangerous tool.
        if self._approval is not None:
            req = self._approval.request(tool.name, "execute", str(kwargs))
            if getattr(req, "status", None) is not None and str(req.status).upper() not in (
                "APPROVED",
            ):
                raise PermissionError(f"dangerous tool '{tool.name}' requires approval")
        # kwargs carry the command/args to sandbox; default echo passthrough.
        command = kwargs.get("command") or [str(kwargs.get("arg", ""))]
        result = self._sandbox.execute(command, label=f"tool:{tool.name}")
        return result

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def has(self, name: str) -> bool:
        return name in self._tools
