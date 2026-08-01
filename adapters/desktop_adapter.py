"""Desktop adapters (Stage 31)."""
from __future__ import annotations

from typing import Tuple

from contracts import IDesktop


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
    """Real desktop automation via PyAutoGUI. Lazy-fail if not installed."""

    def __init__(self) -> None:
        self._pg = None
        self._Image = None

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
