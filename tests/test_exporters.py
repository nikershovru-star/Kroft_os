"""Stage 23 - Graph Export tests (6).

adapters/exporters/ serialize a graph dict (the shape returned by
IGraphBuilder.get_graph(): {"nodes": [...], "edges": [...]}) into DOT (Graphviz),
JSON, and GEXF (Gephi). The exporters live in adapters/ (the only place that
touches external serialization formats); tests drive them directly on a plain
graph dict -- no kernel, no fs, no real vault needed.

Regression note: export_dot/json/gexf must not mutate the input dict.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from adapters.exporters import export_dot, export_json, export_gexf

# A small representative graph: two nodes, one directed edge with a relation.
_SAMPLE = {
    "nodes": [
        {"id": "A.md", "label": "Alpha", "meta": {"tags": ["todo"]}},
        {"id": "B.md", "label": 'Qu"ote', "meta": {}},
    ],
    "edges": [
        {"from": "A.md", "to": "B.md", "relation": "links_to"},
    ],
}


def test_export_dot_basic():
    """DOT contains a digraph, both nodes, and the labeled edge."""
    out = export_dot(_SAMPLE)
    assert out.startswith("digraph KnowledgeOS {")
    assert '"A.md" [label="Alpha"];' in out
    # Quotes in the label must be escaped.
    assert '"B.md" [label="Qu\\"ote"];' in out
    assert '"A.md" -> "B.md" [label="links_to"];' in out
    assert out.rstrip().endswith("}")


def test_export_dot_empty():
    """Empty graph -> valid empty digraph."""
    out = export_dot({"nodes": [], "edges": []})
    assert out == "digraph KnowledgeOS {\n}"


def test_export_json_roundtrip():
    """JSON export is a faithful, UTF-8-safe round-trip of the input graph."""
    out = export_json(_SAMPLE)
    restored = json.loads(out)
    # Structural equality (order-insensitive on dict keys).
    assert restored == _SAMPLE
    # UTF-8 preserved (ensure_ascii=False): label survives intact.
    assert "Alpha" in out


def test_export_json_does_not_mutate_input():
    """Exporter must not mutate the caller's graph dict (snapshot-on-read)."""
    import copy
    before = copy.deepcopy(_SAMPLE)
    export_json(_SAMPLE)
    assert _SAMPLE == before


def test_export_gexf_valid_xml():
    """GEXF output parses as XML and carries the right nodes/edges."""
    out = export_gexf(_SAMPLE)
    root = ET.fromstring(out)
    # xmlns + version present.
    assert root.get("version") == "1.3"
    # Locate graph/nodes/edges (namespace-agnostic).
    graph_el = root.find(".//{http://www.gexf.net/1.3}graph")
    assert graph_el is not None
    assert graph_el.get("defaultedgetype") == "directed"
    nodes_el = graph_el.find("{http://www.gexf.net/1.3}nodes")
    edges_el = graph_el.find("{http://www.gexf.net/1.3}edges")
    node_ids = [n.get("id") for n in nodes_el.findall("{http://www.gexf.net/1.3}node")]
    assert node_ids == ["A.md", "B.md"]
    edge_els = edges_el.findall("{http://www.gexf.net/1.3}edge")
    assert len(edge_els) == 1
    assert edge_els[0].get("source") == "A.md"
    assert edge_els[0].get("target") == "B.md"


def test_export_gexf_edge_ids_are_sequential():
    """Edge XML ids must be 0-based sequential integers (Gephi-compatible)."""
    multi = {
        "nodes": [{"id": "X", "label": "X"}, {"id": "Y", "label": "Y"}, {"id": "Z", "label": "Z"}],
        "edges": [
            {"from": "X", "to": "Y", "relation": "a"},
            {"from": "Y", "to": "Z", "relation": "b"},
        ],
    }
    root = ET.fromstring(export_gexf(multi))
    edges_el = root.find(".//{http://www.gexf.net/1.3}edges")
    ids = [e.get("id") for e in edges_el.findall("{http://www.gexf.net/1.3}edge")]
    assert ids == ["0", "1"]
