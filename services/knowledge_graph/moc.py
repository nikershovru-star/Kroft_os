"""MOC Exporter (TZ-KNOW-001 WP-07, ADR-036).
Generates human-readable Obsidian MOCs with wiki-links and backlinks.
K1-compliant: contracts + stdlib + pathlib.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from contracts.knowledge_graph import NodeType
from .engine import InMemoryGraphEngine

class MOCExporter:
    def __init__(self, engine: InMemoryGraphEngine) -> None:
        self._engine = engine

    def export_adr_moc(self, output_dir: Optional[str] = None) -> Path:
        d = Path(output_dir) if output_dir else Path("docs/architecture/MOCs")
        d.mkdir(parents=True, exist_ok=True)
        lines = ["# ADR Graph MOC", "", "> Machine-generated from knowledge graph. Do not edit by hand.", ""]
        # Group by status
        by_status: dict = {}
        for n in self._engine.nodes():
            if n.type == NodeType.ADR:
                st = n.metadata.get("status", "unknown")
                by_status.setdefault(st, []).append(n)
        for st in sorted(by_status):
            lines.append(f"## Status: {st}")
            for n in sorted(by_status[st], key=lambda x: x.id):
                lines.append(f"- [[{n.id}]] — {n.label}")
                # backlinks
                backs = [e.source_id for e in self._engine.edges() if e.target_id == n.id]
                if backs:
                    lines.append(f"  - referenced by: {', '.join(sorted(set(backs)))}")
            lines.append("")
        path = d / "ADR-Graph-MOC.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def export_capability_map(self, output_dir: Optional[str] = None) -> Path:
        d = Path(output_dir) if output_dir else Path("docs/architecture/MOCs")
        d.mkdir(parents=True, exist_ok=True)
        lines = ["# Capability Map MOC", ""]
        for n in self._engine.nodes():
            if n.type == NodeType.CAPABILITY:
                lines.append(f"- {n.id}: {n.label}")
        path = d / "Capability-Map-MOC.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def export_evidence_map(self, output_dir: Optional[str] = None) -> Path:
        d = Path(output_dir) if output_dir else Path("docs/architecture/MOCs")
        d.mkdir(parents=True, exist_ok=True)
        lines = ["# Evidence Map MOC", "", "ADR → Tests / Experiments", ""]
        for n in self._engine.nodes():
            if n.type == NodeType.ADR:
                backs = [e.source_id for e in self._engine.edges()
                         if e.target_id == n.id and e.type.value in ("VALIDATES", "PROVES")]
                if backs:
                    lines.append(f"- [[{n.id}]] validated by: {', '.join(sorted(set(backs)))}")
        path = d / "Evidence-Map-MOC.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
