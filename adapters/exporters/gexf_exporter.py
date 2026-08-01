"""GEXF (Gephi) exporter (Stage 23)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict
from xml.dom import minidom


def export_gexf(graph: Dict[str, Any]) -> str:
    """Render a graph dict as a GEXF 1.3 XML document (pretty-printed)."""
    root = ET.Element(
        "gexf", xmlns="http://www.gexf.net/1.3", version="1.3"
    )
    graph_el = ET.SubElement(root, "graph", defaultedgetype="directed")
    nodes_el = ET.SubElement(graph_el, "nodes")
    for n in graph.get("nodes", []):
        ET.SubElement(
            nodes_el, "node", id=n["id"], label=n.get("label", n["id"])
        )
    edges_el = ET.SubElement(graph_el, "edges")
    for i, e in enumerate(graph.get("edges", [])):
        ET.SubElement(
            edges_el,
            "edge",
            id=str(i),
            source=e["from"],
            target=e["to"],
        )
    rough = ET.tostring(root, encoding="unicode")
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent="  ")
