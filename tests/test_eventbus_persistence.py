"""Stage 9 - EventBus persistence via IFileSystem (JSONL) tests."""
import json
import tempfile
import os
import glob

import pytest

from adapters import LocalFileSystemAdapter
from infrastructure import InMemoryEventBus
from contracts import IEventBus


@pytest.fixture
def store():
    base = tempfile.mkdtemp()
    adapter = LocalFileSystemAdapter(base)
    yield adapter
    import shutil
    shutil.rmtree(base, ignore_errors=True)


def test_publish_without_store():
    bus = InMemoryEventBus()  # store=None -> in-memory only
    bus.publish_sync("t.a", {"x": 1})
    assert len(bus.get_history("t.a")) == 1
    # nothing on disk (no store)
    assert bus._store is None


def test_publish_with_store(store):
    bus = InMemoryEventBus(store=store, base_path="events")
    bus.publish_sync("t.b", {"x": 2})
    found = glob.glob(os.path.join(store._base, "events", "t.b", "*.jsonl"))
    assert found, "no jsonl file created"
    content = open(found[0], encoding="utf-8").read()
    rec = json.loads(content.strip())
    assert rec["topic"] == "t.b"
    assert rec["event"]["x"] == 2


def test_get_history_from_disk(store):
    # publish with one bus instance
    bus1 = InMemoryEventBus(store=store, base_path="events")
    bus1.publish_sync("t.c", {"n": 1})
    # simulate restart: brand new bus instance, same store
    bus2 = InMemoryEventBus(store=store, base_path="events")
    history = bus2.get_history("t.c")
    assert len(history) == 1
    assert history[0]["n"] == 1


def test_multiple_topics_separate_files(store):
    bus = InMemoryEventBus(store=store, base_path="events")
    bus.publish_sync("topicA", {"v": "a"})
    bus.publish_sync("topicB", {"v": "b"})
    files_a = glob.glob(os.path.join(store._base, "events", "topicA", "*.jsonl"))
    files_b = glob.glob(os.path.join(store._base, "events", "topicB", "*.jsonl"))
    assert files_a and files_b
    assert os.path.dirname(files_a[0]) != os.path.dirname(files_b[0])


def test_clear_history_removes_files(store):
    bus = InMemoryEventBus(store=store, base_path="events")
    bus.publish_sync("t.d", {"v": 1})
    assert glob.glob(os.path.join(store._base, "events", "t.d", "*.jsonl"))
    bus.clear_history()
    assert not glob.glob(os.path.join(store._base, "events", "t.d", "*.jsonl"))


def test_history_merge_memory_and_disk(store):
    bus1 = InMemoryEventBus(store=store, base_path="events")
    bus1.publish_sync("t.e", {"on": "disk"})
    # new bus: in-memory empty, disk has 1
    bus2 = InMemoryEventBus(store=store, base_path="events")
    bus2.publish_sync("t.e", {"on": "memory"})
    history = bus2.get_history("t.e")
    assert len(history) == 2
    sources = {h.get("on") for h in history}
    assert sources == {"disk", "memory"}


def test_jsonl_format_human_readable(store):
    bus = InMemoryEventBus(store=store, base_path="events")
    bus.publish_sync("t.f", {"msg": "привет", "n": 3})
    found = glob.glob(os.path.join(store._base, "events", "t.f", "*.jsonl"))[0]
    with open(found, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            assert line  # non-empty
            rec = json.loads(line)  # valid JSON per line
            assert "topic" in rec and "event" in rec


def test_arch_gate_no_new_dependencies():
    import ast
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent
    src = (ROOT / "infrastructure" / "eventbus.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = {"kernel", "runtime", "adapters"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            top = (node.module or "").split(".")[0]
            if top in forbidden:
                violations.append(f"{node.lineno}: {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in forbidden:
                    violations.append(f"{node.lineno}: {alias.name}")
    assert not violations, f"axis violation: {violations}"
    assert isinstance(InMemoryEventBus(), IEventBus)
