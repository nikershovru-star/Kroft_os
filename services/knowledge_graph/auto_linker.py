"""ADR Auto-Linker (TZ-KNOW-001 WP-04, ADR-036).
Extracts implicit relations from ADR markdown frontmatter + body.
K1-compliant: contracts + stdlib + re.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import List
from contracts.knowledge_graph import Edge, EdgeType, Node, NodeType
from .engine import InMemoryGraphEngine

_ADR_RE = re.compile(r"ADR-\d{3}")
_RFC_RE = re.compile(r"RFC-\d{3}")
_TZ_RE = re.compile(r"TZ-[A-Z]+-\d{3}")
_WP_RE = re.compile(r"WP-\d{2,}")

class ADRAutoLinker:
    def __init__(self, engine: InMemoryGraphEngine) -> None:
        self._engine = engine

    def extract_from_frontmatter(self, adr_id: str, text: str) -> List[Edge]:
        edges: List[Edge] = []
        # related: [ADR-032, RFC-006]  or  related: ["ADR-032", "RFC-006"]
        m = re.search(r"related:\s*\[(.*?)\]", text, re.S)
        if m:
            for token in re.split(r"[\s,']+", m.group(1)):
                token = token.strip()
                # frontmatter `related` carries ADR->ADR references (RFC/TZ/WP
                # are linked from the body via extract_from_body)
                if token and token.startswith("ADR-"):
                    edges.append(Edge(source_id=adr_id, target_id=token, type=EdgeType.REFERENCES))
        return edges

    def extract_from_body(self, adr_id: str, text: str) -> List[Edge]:
        edges: List[Edge] = []
        for m in _ADR_RE.finditer(text):
            tid = m.group(0)
            if tid != adr_id:
                etype = self._classify_edge(text, m.start())
                edges.append(Edge(source_id=adr_id, target_id=tid, type=etype))
        for m in _RFC_RE.finditer(text):
            tid = m.group(0)
            etype = self._classify_edge(text, m.start())
            edges.append(Edge(source_id=adr_id, target_id=tid, type=etype))
        return edges

    def process_adr_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        adr_id = path.stem.split()[0]  # "ADR-032 Security Architecture.md" -> "ADR-032"
        for e in self.extract_from_frontmatter(adr_id, text):
            self._try_add(e)
        for e in self.extract_from_body(adr_id, text):
            self._try_add(e)

    def _try_add(self, e: Edge) -> None:
        if self._engine.get_node(e.source_id) and self._engine.get_node(e.target_id):
            self._engine.add_edge(e)

    @staticmethod
    def _classify_edge(text: str, pos: int) -> EdgeType:
        window = text[max(0, pos-60):pos+60].lower()
        if "superseded" in window or "заменён" in window or "отменён" in window:
            return EdgeType.SUPERSEDES
        if "depends" in window or "зависит" in window:
            return EdgeType.DEPENDS_ON
        if "validates" in window or "подтверждает" in window:
            return EdgeType.VALIDATES
        if "proves" in window or "доказывает" in window:
            return EdgeType.PROVES
        if "violates" in window or "нарушает" in window:
            return EdgeType.VIOLATES
        return EdgeType.REFERENCES
