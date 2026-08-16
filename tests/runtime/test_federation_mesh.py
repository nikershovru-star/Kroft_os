"""PHASE 5 — Local KROFT Network federation mesh (real TCP, slow).

Boot TWO KroftRuntime instances with federation=True; each wires the EXISTING
TcpEventBus (ADR-030 substrate, reused — no duplicate transport) as its IEventBus
and joins the peer. Proves the runtimes form a real mesh: after start, each
node's bus reports the other as a connected peer. No KROFT internals touched;
KroftRuntime stays axis-clean (bus injected from composition layer).

Run: pytest tests/runtime/test_federation_mesh.py -m slow
"""

import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition.kroft_runtime_factory import build_runtime  # noqa: E402


@pytest.mark.slow
def test_federation_mesh_two_nodes_connected():
    with tempfile.TemporaryDirectory() as tmp:
        va = str(Path(tmp) / "nodeA")
        vb = str(Path(tmp) / "nodeB")

        rt_a = build_runtime(node_id="A", vault=va, host="127.0.0.1",
                             api_port=8261, network_port=8361,
                             federation=True, peers=("127.0.0.1:8362",),
                             llm="none", embedding="none")
        rt_b = build_runtime(node_id="B", vault=vb, host="127.0.0.1",
                             api_port=8262, network_port=8362,
                             federation=True, peers=("127.0.0.1:8361",),
                             llm="none", embedding="none")
        try:
            rt_a.start()
            # B joins A (seed node).
            rt_b.start()

            bus_a = rt_a.container.resolve("IEventBus")
            bus_b = rt_b.container.resolve("IEventBus")

            # Deterministic barrier: wait until both nodes see at least one peer
            # (no blind sleep). TcpEventBus.peers() returns connected socket
            # addresses — the initiating side keys by seed addr, the accepting
            # side by the peer's ephemeral socket addr; either way non-empty = mesh.
            deadline = time.time() + 10.0
            connected = False
            while time.time() < deadline:
                if bus_a.peers() and bus_b.peers():
                    connected = True
                    break
                time.sleep(0.1)
            assert connected, (
                f"mesh not connected: A.peers={bus_a.peers()} B.peers={bus_b.peers()}"
            )

            # Both runtimes report running + federation bus present.
            assert rt_a.is_running and rt_b.is_running
            assert rt_a.health()["status"] == "ok"
            assert rt_b.health()["status"] == "ok"
        finally:
            rt_a.stop()
            rt_b.stop()
        assert not rt_a.is_running and not rt_b.is_running
