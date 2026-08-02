"""AKB Sync Adapter (TZ-KNOW-001 WP-03, ADR-036).
Bidirectional: reads AKB YAMLs into the graph; exports graph to
knowledge_graph.yaml + MOC markdown. Never modifies existing AKB files
(adrs.yaml, rfcs.yaml) directly — read-only import, write to new file.
K1-compliant: contracts + stdlib + pathlib.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from contracts.knowledge_graph import (
    Edge,
    EdgeType,
    IGraphSync,
    Node,
    NodeType,
)
from .engine import InMemoryGraphEngine

class AKBSyncAdapter(IGraphSync):
    def __init__(self, engine: InMemoryGraphEngine,
                 root: Optional[str] = None) -> None:
        self._engine = engine
        self._root = Path(root) if root else Path("docs/architecture")

    def import_from_akb(self, akb_path: Optional[str] = None) -> None:
        base = Path(akb_path) if akb_path else self._root
        akb = base / "AKB"
        if not akb.exists():
            # caller may have passed the AKB directory directly
            akb = base if (base / "adrs.yaml").exists() else akb
        # 1) ADRs
        adrs_yaml = akb / "adrs.yaml"
        if adrs_yaml.exists():
            data = yaml.safe_load(adrs_yaml.read_text(encoding="utf-8"))
            for a in data.get("adrs", []):
                self._ensure_node(a["id"], NodeType.ADR, label=a.get("title", a["id"]),
                                  metadata={"status": a.get("status"), "evidence_level": a.get("evidence_level")})
                for rel in a.get("related", []):
                    self._ensure_edge(a["id"], rel, EdgeType.REFERENCES)
        # 2) RFCs
        rfcs_yaml = akb / "rfcs.yaml"
        if rfcs_yaml.exists():
            data = yaml.safe_load(rfcs_yaml.read_text(encoding="utf-8"))
            for r in data.get("rfcs", []):
                self._ensure_node(r["id"], NodeType.RFC, label=r.get("title", r["id"]),
                                  metadata={"status": r.get("status")})
        # 3) History → Experiment nodes
        hist_yaml = akb / "history.yaml"
        if hist_yaml.exists():
            data = yaml.safe_load(hist_yaml.read_text(encoding="utf-8"))
            for h in data.get("history", []):
                hid = h.get("id", "hist-" + str(hash(json.dumps(h, sort_keys=True, default=str)) % 100000))
                self._ensure_node(hid, NodeType.EXPERIMENT, label=hid,
                                  metadata={"tz": h.get("tz"), "status": h.get("status")})
                if h.get("tz"):
                    self._ensure_edge(hid, h["tz"], EdgeType.PROVES)
        # 4) Laws
        laws_yaml = akb / "laws.yaml"
        if laws_yaml.exists():
            data = yaml.safe_load(laws_yaml.read_text(encoding="utf-8"))
            for law in data.get("laws", []):
                lid = law.get("id", "LAW-" + law.get("name", "unknown"))
                self._ensure_node(lid, NodeType.LAW, label=lid,
                                  metadata={"severity": law.get("severity")})
        # 5) Pattern library
        pl_yaml = akb / "pattern_library.yaml"
        if pl_yaml.exists():
            data = yaml.safe_load(pl_yaml.read_text(encoding="utf-8"))
            for pid, pval in data.get("patterns", {}).items():
                self._ensure_node(pid, NodeType.PATTERN, label=pid,
                                  metadata={"category": pval.get("category")})

    def export_to_akb(self, akb_path: Optional[str] = None) -> None:
        base = Path(akb_path) if akb_path else self._root / "AKB"
        base.mkdir(parents=True, exist_ok=True)
        out = base / "knowledge_graph.yaml"
        if out.exists():
            shutil.copy(out, out.with_suffix(".yaml.bak"))
        from enum import Enum
        def _prim(o):
            if isinstance(o, Enum):
                return o.value
            if isinstance(o, dict):
                return {k: _prim(v) for k, v in o.items()}
            return o
        payload = {
            "nodes": [_prim(n.__dict__) for n in self._engine.nodes()],
            "edges": [_prim(e.__dict__) for e in self._engine.edges()],
        }
        out.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                       encoding="utf-8")

    def export_to_moc(self, output_dir: Optional[str] = None) -> None:
        d = Path(output_dir) if output_dir else self._root / "MOCs"
        d.mkdir(parents=True, exist_ok=True)
        # ADR-Graph-MOC.md
        lines = ["# ADR Graph MOC", "", "```kroft-graph", ""]
        for n in self._engine.nodes():
            if n.type == NodeType.ADR:
                lines.append(f"- [[{n.id}]] — {n.label} ({n.metadata.get('status','?')})")
        lines.append("```")
        (d / "ADR-Graph-MOC.md").write_text("\n".join(lines), encoding="utf-8")

    def _ensure_node(self, nid: str, ntype: NodeType, label: str,
                     metadata: Optional[Dict[str, Any]] = None) -> None:
        if self._engine.get_node(nid) is None:
            self._engine.add_node(Node(id=nid, type=ntype, label=label, metadata=metadata or {}))

    def _ensure_edge(self, src: str, tgt: str, etype: EdgeType) -> None:
        if self._engine.get_node(src) and self._engine.get_node(tgt):
            self._engine.add_edge(Edge(source_id=src, target_id=tgt, type=etype))
