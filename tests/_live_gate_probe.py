"""Isolated probe proving live-gate mechanism (P2-F, no Ollama, no external deps).

This file is NOT a real live test. It exists so tests/test_ci_live_gate.py can
assert that setting PROBE_LIVE=1 actually removes the skip on a gated test, while
PROBE_LIVE unset keeps it skipped. Mirrors the exact mechanism real *_LIVE tests use.
"""
import os

import pytest

PROBE = os.environ.get("PROBE_LIVE", "0") == "1"


@pytest.mark.skipif(not PROBE, reason="set PROBE_LIVE=1 to run probe")
def test_probe_live_active_when_flag_set():
    # runs only when PROBE_LIVE=1; if it runs, the gate works
    assert True
