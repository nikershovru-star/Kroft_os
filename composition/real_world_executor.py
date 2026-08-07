"""Real-World Executor Adapter (ТЗ-PHASE-O.1 / O.2).

Minimal IExecutor that routes an Action to REAL execution backends, reusing existing
components (K5) and touching NO kernel/contracts code (K6):

  Action.kind == "file"         -> LocalFileSystemAdapter (read/write)   [adapters/filesystem_adapter.py]
  Action.kind == "command"      -> TerminalExecutor (secure, blacklist)   [services/security/terminal_executor.py]
  Action.kind == "shell"        -> TerminalExecutor (secure, blacklist)   [services/security/terminal_executor.py]
  Action.kind == "execute_plan" -> TerminalExecutor over ALL plan steps (real OS exec)
  Action.kind == "desktop"      -> PyAutoGUIAdapter (click/type/open_app) [adapters/desktop_adapter.py]
  unknown kind                  -> ReferenceExecutor / ReferenceExecutionEnvironment (sim fallback)

Lives in composition/ (the composition root) because it wires adapters together;
adapters/ is forbidden from importing services/ by the arch-gate (K6/V3), so the
cross-layer join belongs here. Implements the existing IExecutor contract; no new
port/interface/DTO/runtime layer. Wired from run_kroft via CognitiveKernel.attach_executor
(ТЗ-EX-01 / PHASE N).
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from contracts.cognitive_domain import (
    Action, CausalMark, ConfidenceScore, NodeLamportClock, Provenance, ProvenanceType,
)
from contracts.i_execution import ExecutionResult, IExecutor
from kernel.execution import ReferenceExecutor, ReferenceExecutionEnvironment


class RealWorldExecutor(IExecutor):
    """Routes Action.kind to a real backend; unknown kinds fall back to the sim env.

    File operations are confined to ``base_dir`` (LocalFileSystemAdapter sandbox); when
    None, a temp dir is used so the real backend is exercised safely by default.
    """

    def __init__(self, clock: Optional[NodeLamportClock] = None,
                 base_dir: Optional[str] = None) -> None:
        self._base_dir = base_dir or tempfile.gettempdir()
        self._fs = None
        self._sandbox = None
        self._desktop = None
        self._sim = ReferenceExecutor(environment=ReferenceExecutionEnvironment(clock), clock=clock)

    # --- backend accessors (lazy, keep imports localized) -------------------
    def _get_fs(self):
        if self._fs is None:
            from adapters.filesystem_adapter import LocalFileSystemAdapter
            self._fs = LocalFileSystemAdapter(self._base_dir)
        return self._fs

    def _get_terminal(self):
        if self._sandbox is None:
            from services.security.terminal_executor import TerminalExecutor
            self._sandbox = TerminalExecutor()
        return self._sandbox

    def _get_desktop(self):
        if self._desktop is None:
            from adapters.desktop_adapter import PyAutoGUIAdapter
            self._desktop = PyAutoGUIAdapter()
        return self._desktop

    # --- IExecutor ---------------------------------------------------------
    def execute(self, action: Action, timeout: Optional[float] = None) -> ExecutionResult:
        kind = (action.kind or "").lower()
        if kind == "file":
            return self._exec_file(action)
        if kind in ("command", "shell", "execute_plan"):
            return self._exec_plan(action, timeout)
        if kind == "desktop":
            return self._exec_desktop(action)
        # unknown kind -> deterministic simulation (backward compatible)
        return self._sim.execute(action, timeout)

    # --- backends ----------------------------------------------------------
    def _exec_file(self, action: Action) -> ExecutionResult:
        mark = CausalMark("realworld", 1)
        conf = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        payload = action.payload or ""
        try:
            if payload.startswith("write:"):
                _, rest = payload.split("write:", 1)
                path, _, content = rest.partition("|")
                ok = self._get_fs().write_content(path.strip(), content)
                return ExecutionResult(
                    action_id=action.id, success=bool(ok),
                    observation=f"file_written:{path}" if ok else "file_write_failed",
                    reward=0.9 if ok else 0.0, confidence=conf, causal=mark)
            if payload.startswith("read:"):
                path = payload.split("read:", 1)[1].strip()
                data = self._get_fs().read_content(path)
                return ExecutionResult(
                    action_id=action.id, success=True,
                    observation=f"file_read:{len(data)} bytes", reward=0.9,
                    confidence=conf, causal=mark)
            return ExecutionResult(
                action_id=action.id, success=False,
                observation="file: unknown op (use write:path|content or read:path)",
                reward=0.0, confidence=conf, causal=mark)
        except Exception as exc:  # noqa: BLE001 — real backend errors must not crash the loop
            return ExecutionResult(
                action_id=action.id, success=False,
                observation=f"file_error:{exc}", reward=0.0, confidence=conf, causal=mark)

    def _exec_plan(self, action: Action, timeout: Optional[float] = None) -> ExecutionResult:
        """Execute EVERY plan step as a real action, aggregate result.

        Two input shapes are supported (backward compatible):
          * STRUCTURED: payload is a JSON array of step objects, each with a 'kind'
            ('file' | 'command' | 'shell' | 'desktop'). Routed precisely.
          * TEXTUAL: payload is "\\n".join(plan.steps) (kernel default). Each line is
            routed heuristically: 'write:' -> file, 'click'/'type'/'open_app' -> desktop,
            otherwise -> TerminalExecutor (echo proof).

        Aggregate: all steps must succeed.
        """
        mark = CausalMark("realworld", 1)
        conf = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        structured = self._parse_structured_plan(action.payload)
        if structured is not None:
            steps = structured
            observations = []
            all_ok = True
            try:
                for i, step in enumerate(steps):
                    r = self._exec_structured_step(action.id, i, step, conf, mark, timeout)
                    observations.append(r.observation)
                    all_ok = all_ok and r.success
                return ExecutionResult(
                    action_id=action.id, success=all_ok,
                    observation="; ".join(observations)[:400] or "plan_done",
                    reward=0.9 if all_ok else 0.1, confidence=conf, causal=mark)
            except Exception as exc:  # noqa: BLE001
                return ExecutionResult(
                    action_id=action.id, success=False,
                    observation=f"plan_error:{exc}", reward=0.0, confidence=conf, causal=mark)

        # --- textual fallback (kernel default) ---
        steps = [s.strip() for s in (action.payload or "").splitlines() if s.strip()]
        if not steps:
            steps = ["echo ok"]
        observations = []
        all_ok = True
        try:
            for step in steps:
                low = step.lower()
                if low.startswith("write:"):
                    r = self._exec_file(Action(id=f"{action.id}-f", kind="file",
                                               payload=step, confidence=conf,
                                               provenance=action.provenance))
                elif "click" in low or "type" in low or "open_app" in low:
                    r = self._route_desktop_step(action.id, step, conf, mark)
                else:
                    r = self._run_shell(step, timeout)
                observations.append(r.observation)
                all_ok = all_ok and r.success
            return ExecutionResult(
                action_id=action.id, success=all_ok,
                observation="; ".join(observations)[:400] or "plan_done",
                reward=0.9 if all_ok else 0.1, confidence=conf, causal=mark)
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                action_id=action.id, success=False,
                observation=f"plan_error:{exc}", reward=0.0, confidence=conf, causal=mark)

    # --- external bridge (ТЗ-PHASE-O.5) -----------------------------------
    def run_plan(self, payload: str, timeout: Optional[float] = None) -> ExecutionResult:
        """Bridge for external agents/users to execute a plan via the real backend.

        Accepts EITHER a structured JSON-array plan (passed through unchanged) OR a
        textual "\\n".join(steps) plan (existing heuristic routing). Builds the
        Action(kind="execute_plan") and delegates to execute() — no planner/CognitiveKernel
        change (K6). This is the minimal entry point that lets an external source drive
        RealWorldExecutor directly without invoking the full cognitive cycle.
        """
        action = Action(id="ext-plan", kind="execute_plan", payload=payload or "",
                        confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                        provenance=Provenance(source="external", actor="bridge"))
        return self.execute(action, timeout)

    @staticmethod
    def _parse_structured_plan(payload: str):
        """Return a list of step dicts if payload is a JSON array of kinded objects, else None."""
        if not payload or not payload.strip().startswith("["):
            return None
        try:
            import json
            data = json.loads(payload)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, list) or not data or not all(isinstance(s, dict) and "kind" in s for s in data):
            return None
        return data

    def _exec_structured_step(self, action_id, idx, step, conf, mark, timeout) -> ExecutionResult:
        kind = (step.get("kind") or "").lower()
        if kind == "file":
            path = step.get("path", "")
            content = step.get("content", "")
            return self._exec_file(Action(id=f"{action_id}-{idx}", kind="file",
                                          payload=f"write:{path}|{content}", confidence=conf,
                                          provenance=Provenance(source="plan", actor="executor")))
        if kind in ("command", "shell"):
            return self._run_shell(step.get("cmd", "echo ok"), timeout)
        if kind == "desktop":
            # step: {"kind":"desktop","op":"click","x":..,"y":..} | {"op":"type","text":..} | {"op":"open_app","name":..}
            op = (step.get("op") or "").lower()
            line = op
            if op == "click":
                line = f"click {step.get('x', 0)} {step.get('y', 0)}"
            elif op == "type":
                line = f"type {step.get('text', '')}"
            elif op == "open_app":
                line = f"open_app {step.get('name', '')}"
            return self._route_desktop_step(f"{action_id}-{idx}", line, conf, mark)
        # unknown structured kind -> sim fallback for that step
        return self._sim.execute(
            Action(id=f"{action_id}-{idx}", kind=kind, payload="", confidence=conf,
                   provenance=Provenance(source="plan", actor="executor")), timeout)

    def _run_shell(self, cmd_line: str, timeout: Optional[float] = None) -> ExecutionResult:
        mark = CausalMark("realworld", 1)
        conf = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        # TerminalExecutor (services/security) takes a command STRING and applies the
        # blacklist; returns TerminalResult(returncode, out, err, blocked).
        result = self._get_terminal().execute(cmd_line, timeout=timeout or 30.0)
        rc = getattr(result, "returncode", -1)
        blocked = bool(getattr(result, "blocked", False))
        success = (rc == 0) and not blocked
        out = (getattr(result, "out", "") or getattr(result, "err", "") or "").strip()
        return ExecutionResult(
            action_id="shell", success=success,
            observation=(f"blocked:{out}" if blocked else (out[:200] or "command_done")),
            reward=0.9 if success else 0.1, confidence=conf, causal=mark)

    def _route_desktop_step(self, action_id, step, conf, mark) -> ExecutionResult:
        d = self._get_desktop()
        low = step.lower()
        try:
            if low.startswith("click"):
                parts = step.split()
                x = int(parts[1]) if len(parts) > 1 else 0
                y = int(parts[2]) if len(parts) > 2 else 0
                d.click(x, y)
                obs = f"desktop_click:{x},{y}"
            elif low.startswith("type"):
                text = step.split(" ", 1)[1] if " " in step else ""
                d.type(text)
                obs = f"desktop_type:{len(text)} chars"
            elif low.startswith("open_app"):
                name = step.split(" ", 1)[1] if " " in step else ""
                d.open_app(name)
                obs = f"desktop_open:{name}"
            else:
                obs = "desktop_noop"
            return ExecutionResult(action_id=action_id, success=True,
                                    observation=obs, reward=0.9, confidence=conf, causal=mark)
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(action_id=action_id, success=False,
                                    observation=f"desktop_error:{exc}", reward=0.0,
                                    confidence=conf, causal=mark)

    def _exec_desktop(self, action: Action) -> ExecutionResult:
        """kind='desktop': payload lines are desktop actions (click/type/open_app)."""
        mark = CausalMark("realworld", 1)
        conf = ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE)
        steps = [s.strip() for s in (action.payload or "").splitlines() if s.strip()]
        observations = []
        all_ok = True
        for i, step in enumerate(steps):
            r = self._route_desktop_step(f"{action.id}-{i}", step, conf, mark)
            observations.append(r.observation)
            all_ok = all_ok and r.success
        return ExecutionResult(
            action_id=action.id, success=all_ok,
            observation="; ".join(observations)[:400] or "desktop_done",
            reward=0.9 if all_ok else 0.1, confidence=conf, causal=mark)
