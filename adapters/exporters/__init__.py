"""Graph exporters — adapters for external graph formats (Stage 23).

The ONLY place that touches external (non-kernel) serialization formats:
DOT (Graphviz), JSON, and GEXF (Gephi). Each exporter takes a plain
``graph`` dict (the shape returned by ``IGraphBuilder.get_graph()``:
``{"nodes": [...], "edges": [...]}``) and returns a ``str``.

Architecture contract: adapters/ may import contracts + stdlib. These
exporters use ONLY stdlib (no third-party graph libs).
"""
from .dot_exporter import export_dot
from .json_exporter import export_json
from .gexf_exporter import export_gexf

__all__ = ["export_dot", "export_json", "export_gexf"]
