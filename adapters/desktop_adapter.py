"""Desktop adapters (Stage 31)."""
from __future__ import annotations

from typing import Optional, Tuple

from contracts import IDesktop
from contracts.i_execution_sandbox import IExecutionSandbox


class MockDesktopAdapter(IDesktop):
    """No-op desktop adapter for tests and default wiring."""

    def click(self, x: int, y: int) -> None:
        pass

    def type(self, text: str) -> None:
        pass

    def screenshot(self) -> bytes:
        # Minimal 1x1 PNG placeholder (no PIL dependency).
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def cursor_position(self) -> Tuple[int, int]:
        return (0, 0)

    def open_app(self, name: str) -> None:
        pass


class PyAutoGUIAdapter(IDesktop):
    """Real desktop automation via PyAutoGUI. Lazy-fail if not installed.

    open_app is routed through an IExecutionSandbox (TZ-EXECUTION-001, ADR-039)
    to avoid os.system shell injection. GUI automation (click/type/screenshot)
    stays in-process (PyAutoGUI cannot be sandboxed).
    """

    def __init__(self, sandbox: Optional[IExecutionSandbox] = None) -> None:
        self._pg = None
        self._Image = None
        self._sandbox = sandbox

    def _ensure(self):
        if self._pg is None:
            try:
                import pyautogui
                from PIL import Image
                self._pg = pyautogui
                self._Image = Image
            except ImportError as e:
                raise RuntimeError(
                    "PyAutoGUI not installed: pip install pyautogui pillow"
                ) from e

    def available(self) -> bool:
        """Best-effort liveness check used by live tests to skip gracefully.

        True only when PyAutoGUI is importable AND (on posix) a display server is
        present. Lets CI / headless environments skip real GUI automation without
        importing or touching the screen. Never raises.
        """
        try:
            import pyautogui  # noqa: F401  (import side-effects only)
        except ImportError:
            return False
        import os
        if os.name == "posix":
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                return False
        return True

    def click(self, x: int, y: int) -> None:
        self._ensure()
        self._pg.click(x, y)

    def type(self, text: str) -> None:
        self._ensure()
        self._pg.typewrite(text, interval=0.01)

    def screenshot(self) -> bytes:
        self._ensure()
        import io
        img = self._pg.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def cursor_position(self) -> Tuple[int, int]:
        self._ensure()
        return self._pg.position()

    def open_app(self, name: str) -> None:
        # TZ-EXECUTION-001 / ADR-039: route through sandbox (no os.system).
        if self._sandbox is not None:
            import platform
            sys_name = platform.system()
            if sys_name == "Windows":
                cmd = ["cmd", "/c", "start", "", name]
            elif sys_name == "Darwin":
                cmd = ["open", name]
            else:
                cmd = ["xdg-open", name]
            self._sandbox.execute(cmd, label=f"open_app:{name}")
            return
        # Fallback (no sandbox wired): in-process best-effort, no injection.
        self._ensure()
        import os
        import platform
        sys_name = platform.system()
        if sys_name == "Windows":
            os.system(f'start "" "{name}"')
        elif sys_name == "Darwin":
            os.system(f'open "{name}"')
        else:
            os.system(f'xdg-open "{name}" &')
