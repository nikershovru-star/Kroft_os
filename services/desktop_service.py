"""DesktopService — high-level desktop orchestration (Stage 31)."""
from __future__ import annotations

from typing import Optional

from contracts import IDesktop


class DesktopService:
    """Orchestrates IDesktop actions into user-facing workflows."""

    def __init__(self, desktop: Optional[IDesktop] = None) -> None:
        self._desktop = desktop

    def click_at(self, x: int, y: int) -> None:
        if self._desktop is None:
            raise RuntimeError("IDesktop not wired")
        self._desktop.click(x, y)

    def type_text(self, text: str) -> None:
        if self._desktop is None:
            raise RuntimeError("IDesktop not wired")
        self._desktop.type(text)

    def capture_screen(self) -> bytes:
        if self._desktop is None:
            raise RuntimeError("IDesktop not wired")
        return self._desktop.screenshot()

    def where_is_cursor(self) -> tuple:
        if self._desktop is None:
            raise RuntimeError("IDesktop not wired")
        return self._desktop.cursor_position()

    def launch(self, name: str) -> None:
        if self._desktop is None:
            raise RuntimeError("IDesktop not wired")
        self._desktop.open_app(name)
