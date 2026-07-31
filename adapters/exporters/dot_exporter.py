"""DOT (Graphviz) exporter (Stage 23)."""
from __future__ import annotations

from typing import Any, Dict, List


def export_dot(graph: Dict[str, Any]) -> str:
    """Render a graph dict as a Graphviz ``digraph`` in DOT syntax."""
    lines = ["digraph KROFT_OS {"]
    for n in graph.get("nodes", []):
        label = (n.get("label") or n["id"]).replace('"', '\\"')
        lines.append(f'  "{n["id"]}" [label="{label}"];')
    for e in graph.get("edges", []):
        rel = (e.get("relation") or "").replace('"', '\\"')
        lines.append(f'  "{e["from"]}" -> "{e["to"]}" [label="{rel}"];')
    lines.append("}")
    return "\n".join(lines)
