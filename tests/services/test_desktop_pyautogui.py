"""Stage 36 - PyAutoGUIAdapter lazy-fail tests (3)."""
import pytest

from adapters import PyAutoGUIAdapter


class TestPyAutoGUIAdapter:
    def test_lazy_import_fails_cleanly(self):
        a = PyAutoGUIAdapter()
        # If pyautogui not installed, _ensure raises RuntimeError with helpful msg
        with pytest.raises(RuntimeError) as exc:
            a.click(0, 0)
        assert "pip install pyautogui" in str(exc.value)

    def test_screenshot_returns_bytes(self):
        # This test only passes if pyautogui IS installed
        try:
            import pyautogui  # noqa: F401
        except ImportError:
            pytest.skip("pyautogui not installed")
        a = PyAutoGUIAdapter()
        png = a.screenshot()
        assert png.startswith(b"\x89PNG")

    def test_cursor_position_tuple(self):
        try:
            import pyautogui  # noqa: F401
        except ImportError:
            pytest.skip("pyautogui not installed")
        a = PyAutoGUIAdapter()
        x, y = a.cursor_position()
        assert isinstance(x, int) and isinstance(y, int)
