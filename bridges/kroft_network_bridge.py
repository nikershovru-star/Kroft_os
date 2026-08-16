"""KROFT-NET-04 — HERMES MULTI-NODE OPERATOR BRIDGE (TZ §8/§9/§10/§24).

Extends the existing single-node Hermes bridge (kroft_bridge.py) with the operator
surface for a LOCAL network of independent KROFT nodes (TZ §9/§10 final UX):

    kroft.list()                 -> list running nodes
    kroft.status(node)           -> node status
    kroft.search(node, query)    -> delegated to that node's KroftBridge
    kroft.network.list()         -> network overview
    kroft.network.status()       -> network health
    kroft.network.start(node)    -> boot a node via KroftNodeManager
    kroft.network.stop(node)     -> stop a node

Hermes stays the OPERATOR: it never becomes part of CognitiveKernel (TZ §8/§24). This
bridge reuses KroftNodeManager (KROFT-NET-02) and KroftBridge (H0) — no new federation,
no kernel change, K5 reuse.

KROFT-NET-01 guarantee: each managed node gets its own state_root via the manager.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.kroft_node_manager import KroftNodeManager, NodeSpec

from bridges.kroft_bridge import KroftBridge, KroftToolResult


class KroftNetworkBridge:
    """Hermes operator surface over a local KROFT network (TZ §9/§10)."""

    def __init__(self, base_state_root: Optional[str] = None) -> None:
        self._mgr = KroftNodeManager(base_state_root=base_state_root)
        self._bridges: Dict[str, KroftBridge] = {}

    # --- node management (KROFT-NET-02 reuse) ---
    def start_node(self, node_id: str, role: str = "generic", port: int = 7101,
                   state_root: str = "") -> KroftToolResult:
        spec = NodeSpec(id=node_id, role=role, port=port, state_root=state_root)
        try:
            self._mgr.start(spec)
            return KroftToolResult(ok=True, operation="network.start",
                                   result={"node_id": node_id, "status": "starting"})
        except Exception as exc:  # honest, not silent
            return KroftToolResult(ok=False, operation="network.start",
                                   errors=[str(exc)])

    def stop_node(self, node_id: str) -> KroftToolResult:
        stopped = self._mgr.stop(node_id)
        return KroftToolResult(ok=stopped, operation="network.stop",
                               result={"node_id": node_id, "stopped": stopped})

    def list(self) -> KroftToolResult:
        """kroft.list() — nodes Hermes can see (TZ §9/§10)."""
        nodes = [
            {"node_id": s.node_id, "running": s.running, "port": s.port,
             "state_root": s.state_root}
            for s in self._mgr.list_nodes()
        ]
        return KroftToolResult(ok=True, operation="list",
                               result={"nodes": nodes, "count": len(nodes)},
                               metadata={"count": len(nodes)})

    def network_status(self) -> KroftToolResult:
        """kroft.network.status() — network overview (TZ §28)."""
        nodes = self._mgr.list_nodes()
        online = sum(1 for n in nodes if n.running)
        return KroftToolResult(
            ok=True, operation="network.status",
            result={
                "nodes": len(nodes),
                "online": online,
                "offline": len(nodes) - online,
                "details": [
                    {"node_id": n.node_id, "running": n.running, "port": n.port}
                    for n in nodes
                ],
            },
            metadata={"nodes": len(nodes), "online": online},
        )

    # --- per-node delegation (H0 reuse) ---
    def _bridge_for(self, node_id: str) -> KroftBridge:
        if node_id not in self._bridges:
            spec = self._mgr._specs.get(node_id)
            snap = None
            if spec:
                sr = spec.resolved_state_root(self._mgr._base)
                snap = f"{sr}/_snapshot.json"
            self._bridges[node_id] = KroftBridge(snapshot_path=snap, node_id=node_id)
        return self._bridges[node_id]

    def status(self, node_id: str) -> KroftToolResult:
        return self._bridge_for(node_id).status()

    def search(self, node_id: str, query: str, top_k: int = 10) -> KroftToolResult:
        return self._bridge_for(node_id).search(query, top_k=top_k)

    def query(self, node_id: str, query: str, top_k: int = 10) -> KroftToolResult:
        return self._bridge_for(node_id).query(query, top_k=top_k)

    def resolve(self, node_id: str, query: str, resolution: str = "CONCEPT") -> KroftToolResult:
        return self._bridge_for(node_id).resolve(query, resolution=resolution)

    def audit(self, node_id: str, target: str) -> KroftToolResult:
        return self._bridge_for(node_id).audit(target)

    def shutdown_all(self) -> None:
        self._mgr.shutdown_all()


# --- module-level Hermes tool surface (TZ §9) ---
_default: Optional[KroftNetworkBridge] = None


def _network() -> KroftNetworkBridge:
    global _default
    if _default is None:
        _default = KroftNetworkBridge()
    return _default


def kroft_list() -> KroftToolResult:
    return _network().list()


def kroft_network_status() -> KroftToolResult:
    return _network().network_status()


def kroft_network_start(node_id: str, role: str = "generic", port: int = 7101) -> KroftToolResult:
    return _network().start_node(node_id, role=role, port=port)


def kroft_network_stop(node_id: str) -> KroftToolResult:
    return _network().stop_node(node_id)


def kroft_status(node_id: str) -> KroftToolResult:
    return _network().status(node_id)


def kroft_search(node_id: str, query: str, top_k: int = 10) -> KroftToolResult:
    return _network().search(node_id, query, top_k=top_k)


def kroft_query(node_id: str, query: str, top_k: int = 10) -> KroftToolResult:
    return _network().query(node_id, query, top_k=top_k)


def kroft_resolve(node_id: str, query: str, resolution: str = "CONCEPT") -> KroftToolResult:
    return _network().resolve(node_id, query, resolution=resolution)


def kroft_audit(node_id: str, target: str) -> KroftToolResult:
    return _network().audit(node_id, target)
