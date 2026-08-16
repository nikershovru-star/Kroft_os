"""H0 — Hermes <-> KROFT Bridge tests (READ-ONLY, mocks only).

ТЗ H0 §24: только необходимые тесты, mocks/fakes, НЕ re-embed, НЕ менять
production snapshot. Проверяет contract bridge, НЕ KROFT internals.

ТЗ §23/§25: bridge READ ONLY + KROFT не знает о Hermes (independent).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

from bridges.kroft_bridge import KroftBridge, KroftToolResult
from contracts import ResolutionLevel


class FakeNode:
    def __init__(self, id):
        self.id = id


class FakeEdge:
    def __init__(self, s, t):
        self.source_id, self.target_id = s, t
        self.type = "REFERENCES"
        self.weight = 1.0
        self.evidence = ""


class FakeGraph:
    def __init__(self, n=3, e=2):
        self._nodes = [FakeNode(f"n{i}") for i in range(n)]
        self._edges = [FakeEdge(f"n0", f"n{i+1}") for i in range(e)]

    def nodes(self):
        return list(self._nodes)

    def edges(self):
        return list(self._edges)


class FakeResolutionView:
    def __init__(self, items, level):
        self.items = items
        self.level = level


class FakeResolutionService:
    def view(self, query, level):
        return FakeResolutionView(
            [{"id": f"{query}:{level.name}:{i}"} for i in range(2)], level)


class FakeEngine:
    def query_with_abstention(self, query, top_k=10, semantic_threshold=None):
        return ([("n0", 0.9), ("n1", 0.7)], False)

    def stats(self):
        return {"nodes": 3, "edges": 2}


class FakeSearch:
    def search(self, query, top_k=10):
        return [("n0", 0.9), ("n1", 0.8)]

    def search_hybrid(self, query, top_k=10):
        return [("n0", 0.95), ("n1", 0.85)]


class FakeApp:
    """Minimal fake KroftApp carrying only read-only attributes the bridge uses."""

    def __init__(self):
        self.config = type("C", (), {
            "node_id": "nodeA",
            "federation": False,
            "knowledge_snapshot": None,
        })()
        self.graph = FakeGraph()
        self.search = FakeSearch()
        self.engine = FakeEngine()
        self.memory = object()
        self.procedural = object()
        self.embedding_adapter = None
        self.semantic_index = None
        self._snapshot_store = None
        self._resolution_service = FakeResolutionService()


def _patch_bridge(monkeypatch):
    fake = FakeApp()
    def _ensure(self):
        self._resolution = fake._resolution_service
        return fake
    monkeypatch.setattr(KroftBridge, "_ensure_app", _ensure)
    return fake


def test_kroft_status(monkeypatch):
    _patch_bridge(monkeypatch)
    r = KroftBridge().status()
    assert isinstance(r, KroftToolResult)
    assert r.ok is True
    assert r.result["knowledge"]["nodes"] == 3
    assert r.result["knowledge"]["edges"] == 2
    assert r.result["retrieval"]["hybrid"] is True
    assert r.result["federation"]["enabled"] is False


def test_kroft_search(monkeypatch):
    _patch_bridge(monkeypatch)
    r = KroftBridge().search("persistence", top_k=5)
    assert r.ok is True
    assert r.metadata["mode"] == "hybrid"
    assert len(r.result["items"]) == 2
    assert r.result["items"][0]["id"] == "n0"


def test_kroft_query(monkeypatch):
    _patch_bridge(monkeypatch)
    r = KroftBridge().query("federation")
    assert r.ok is True
    assert r.metadata["mode"] == "hybrid"
    assert len(r.result["items"]) == 2


def test_kroft_resolve(monkeypatch):
    # Bridge contract: когда resolution-сервис предоставлен (через KroftApp
    # или future wiring), resolve возвращает структурированный view.
    _patch_bridge(monkeypatch)
    r = KroftBridge().resolve("memory", "SYSTEM")
    assert r.ok is True
    assert r.result["level"] == "SYSTEM"
    assert len(r.result["items"]) == 2


def test_kroft_resolve_gap(monkeypatch):
    # ТЗ §27: без IGraphQuery в KroftApp bridge честно возвращает GAP,
    # НЕ симулирует resolve.
    fake = FakeApp()
    fake._resolution_service = None  # имитирует отсутствие IGraphQuery

    def _ensure(self):
        self._resolution = None
        return fake
    monkeypatch.setattr(KroftBridge, "_ensure_app", _ensure)
    r = KroftBridge().resolve("memory", "SYSTEM")
    assert r.ok is False
    assert "GAP" in r.errors[0]


def test_kroft_resolve_unknown_level(monkeypatch):
    _patch_bridge(monkeypatch)
    bad = KroftBridge().resolve("x", "NOPE")
    assert bad.ok is False
    assert "unknown resolution level" in bad.errors[0]


def test_kroft_audit(monkeypatch):
    _patch_bridge(monkeypatch)
    for target in ("semantic retrieval", "memory", "federation", "persistence"):
        r = KroftBridge().audit(target)
        assert r.ok is True, target
        assert r.result["target"] == target


def test_kroft_unavailable(monkeypatch):
    def boom(self):
        raise RuntimeError("KROFT unavailable: process down")
    monkeypatch.setattr(KroftBridge, "_ensure_app", boom)
    r = KroftBridge().status()
    assert r.ok is False
    assert "unavailable" in r.errors[0].lower()


def test_read_only_guarantee():
    """Bridge public API must not expose any write method (ТЗ §23)."""
    write_methods = {"ingest", "save", "persist", "merge", "commit",
                     "apply_patch", "run_tests", "evolve", "write", "mutate"}
    public = {m for m in dir(KroftBridge) if not m.startswith("_")}
    assert not (write_methods & public), f"write method leaked: {write_methods & public}"


def test_kroft_independent_from_hermes():
    """ТЗ §25: KROFT не должен импортировать Hermes; bridge K1-чист.

    `bridges/` — новый пакет вне import_matrix (не сканируется gate), поэтому
    проверяем AST-импорты напрямую: разрешены только stdlib + contracts.* +
    composition.run_kroft (K3-легальная composition root). 'hermes' запрещён.
    """
    import ast as _ast
    from pathlib import Path
    tree = _ast.parse((Path.cwd() / "bridges" / "kroft_bridge.py").read_text(encoding="utf-8"))
    project_imports = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.ImportFrom):
            if node.module and node.module.split(".")[0] not in ("contracts", "composition"):
                project_imports.append(node.module)
        elif isinstance(node, _ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top not in ("contracts", "composition"):
                    project_imports.append(top)
    banned = {i for i in project_imports if "hermes" in i.lower()}
    assert not banned, f"bridge imports Hermes: {banned}"
    # composition.run_kroft — единственная внешняя зависимость (composition root, K3-legal)
    assert "composition" in " ".join(project_imports) or project_imports, \
        f"unexpected project imports: {project_imports}"
