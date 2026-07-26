"""JSON exporter (Stage 23)."""
from __future__ import annotations

import json
from typing import Any, Dict


def export_json(graph: Dict[str, Any]) -> str:
    """Render a graph dict as pretty-printed JSON (UTF-8 safe)."""
    return json.dumps(graph, ensure_ascii=False, indent=2)
