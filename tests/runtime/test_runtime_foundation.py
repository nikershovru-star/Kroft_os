"""PHASE 1 — KroftRuntime against the REAL composition root + foundation.

Marked ``slow`` (see pytest.ini): loads the production
``KROFT_KNOWLEDGE_FOUNDATION/_snapshot.json`` read-only, so it is excluded from
the default fast suite. Run explicitly with::

    pytest tests/runtime/test_runtime_foundation.py -m slow -o "pythonpath=."

ТЗ §11: the foundation file is loaded, NEVER mutated (build_container does a
read + in-memory restore). This proves ТЗ STEP 10.8 (existing KROFT
functionality available) and STEP 10.9 (foundation snapshot loads).
"""

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.kroft_runtime import KroftRuntime, RuntimeConfig  # noqa: E402
from composition.kroft_runtime_factory import build_runtime  # noqa: E402


@pytest.mark.slow
def test_runtime_boots_real_foundation():
    """Real build_container + CognitiveKernel + KROFT_OSServer with foundation."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = RuntimeConfig(
            node_id="kroft-integration",
            vault=tmp,
            host="127.0.0.1",
            api_port=8211,  # distinct from any default to avoid clashes
            llm="none",
            embedding="none",
        )
        rt = build_runtime(cfg)  # assembly-layer factory injects real builders
        try:
            rt.start()
            assert rt.is_running
            # Foundation snapshot should have loaded real nodes/edges/vectors.
            engine = rt.container.resolve("GraphQueryEngine")
            snap = engine._snapshot()
            assert len(snap.get("nodes", [])) > 0, "foundation nodes missing"
            assert len(snap.get("edges", [])) > 0, "foundation edges missing"
            # Health contract reflects loaded knowledge.
            h = rt.health()
            assert h["status"] == "ok"
            assert h["knowledge"] == "ready"
            assert h["http"] == "ready"
            # Existing KROFT functionality reachable through the runtime.
            assert engine.search("memory") is not None
        finally:
            rt.stop()
        assert not rt.is_running
