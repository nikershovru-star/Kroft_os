"""PHASE 4 — Local KROFT Network: multiple independent Runtimes reachable via HTTP.

Marked ``slow``: boots TWO real KroftRuntime instances (distinct vaults + ports,
real 750MB foundation loaded read-only per instance) and proves a KroftHttpBridge
(Hermes-side client) can talk to each node through the universal HTTP contract.
This is the transport-level "Local KROFT Network" proof — each node is an
independent Runtime; Hermes addresses them individually, never touching KROFT
internals. Federation mesh (crdt/tcp_event_bus) is sibling substrate, out of scope.

Run: pytest tests/runtime/test_multi_node.py -m slow
"""

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition.kroft_runtime_factory import build_runtime  # noqa: E402
from bridges.kroft_bridge import KroftHttpBridge  # noqa: E402


@pytest.mark.slow
def test_local_kroft_network_two_nodes():
    with tempfile.TemporaryDirectory() as tmp:
        va = str(Path(tmp) / "nodeA")
        vb = str(Path(tmp) / "nodeB")

        rt_a = build_runtime(node_id="nodeA", vault=va, host="127.0.0.1",
                             api_port=8241, llm="none", embedding="none")
        rt_b = build_runtime(node_id="nodeB", vault=vb, host="127.0.0.1",
                             api_port=8242, llm="none", embedding="none")
        try:
            rt_a.start()
            rt_b.start()
            assert rt_a.is_running and rt_b.is_running

            # Two independent HTTP endpoints.
            bridge_a = KroftHttpBridge(f"http://127.0.0.1:{rt_a.server.port}",
                                       timeout=30, node_id="nodeA")
            bridge_b = KroftHttpBridge(f"http://127.0.0.1:{rt_b.server.port}",
                                       timeout=30, node_id="nodeB")

            sa = bridge_a.status()
            sb = bridge_b.status()
            assert sa.ok and sb.ok
            # Each node reports its own identity — independent state.
            assert sa.result["node_id"] == "nodeA"
            assert sb.result["node_id"] == "nodeB"

            # Hermes query works against both nodes via the same universal contract.
            qa = bridge_a.query("memory", top_k=3)
            qb = bridge_b.query("federation", top_k=3)
            assert qa.ok and qa.metadata["node"] == "nodeA"
            assert qb.ok and qb.metadata["node"] == "nodeB"
        finally:
            rt_a.stop()
            rt_b.stop()
        assert not rt_a.is_running and not rt_b.is_running
