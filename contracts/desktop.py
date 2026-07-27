"""IDesktop — desktop automation port (Stage 31)."""
from __future__ import annotations

import abc
from typing import Tuple


class IDesktop(abc.ABC):
    """Port for driving the user's desktop (mouse, keyboard, screen, apps)."""

    @abc.abstractmethod
    def click(self, x: int, y: int) -> None:
        """Click at screen coordinates (x, y)."""

    @abc.abstractmethod
    def type(self, text: str) -> None:
        """Type the given text."""

    @abc.abstractmethod
    def screenshot(self) -> bytes:
        """Return PNG bytes of the current screen."""

    @abc.abstractmethod
    def cursor_position(self) -> Tuple[int, int]:
        """Return (x, y) of the mouse cursor."""

    @abc.abstractmethod
    def open_app(self, name: str) -> None:
        """Open an application by name (platform-dependent)."""
