"""Repo-root conftest: hard guard against collecting the git-ignored ``archive/`` tree.

The KROFT_OS ``pytest.ini`` already sets ``norecursedirs = archive`` — but that only takes
effect when pytest's rootdir is the repo. If pytest is launched from a parent dir (e.g. the
Obsidian Vault root) pointing at ``02-Projects/KROFT_OS``, ``pytest.ini`` is not in scope and
the stale ``archive/KnowledgeOS-v5/`` code (a SEPARATE, unmaintained project the owner chose
to keep) gets collected, emitting benign ``\\w``/DeprecationWarnings and unrelated failures.

This conftest is ALWAYS loaded when pytest collects the repo path (regardless of cwd), and
prunes any ``archive`` directory by substring — so the guard holds no matter where pytest is
started. It does NOT modify ``archive/`` (owner decision: leave it untouched); it only excludes
it from collection.
"""

from __future__ import annotations

from pathlib import Path


def pytest_ignore_collect(collection_path: "Path", config) -> bool:
    # collection_path is a pathlib.Path in pytest >= 7.
    parts = collection_path.parts
    # 'archive' is a top-level dir under the repo; also guard the known nested name.
    if "archive" in parts:
        return True
    # Defense in depth: substring match on the full path string.
    if "archive" in str(collection_path) and "KnowledgeOS-v5" in str(collection_path):
        return True
    return False


# ---------------------------------------------------------------------------
# ТЗ-RESTRUCTURE (D6): subsystem markers via path, independent of import-mode.
# Each test file under tests/<sub>/ gets the matching marker so targeted runs work:
#   pytest -m kernel | pytest -m "federation or integration" | pytest -m "not slow"
# (pytestmark in __init__.py is unreliable under the default import mode, so we tag here.)
# ---------------------------------------------------------------------------
_SUBDIR_MARKER = {
    "kernel": "kernel",
    "contracts": "contracts",
    "services": "services",
    "adapters": "adapters",
    "federation": "federation",
    "architecture": "architecture",
    "agent": "agent",
    "agent_orchestration": "agent",
    "graph": "graph",
    "knowledge_graph": "graph",
    "llm": "llm",
    "security": "security",
    "observability": "observability",
    "memory": "memory",
    "integration": "integration",
    "common": "common",
    "tenant": "kernel",
}

# Files that exercise the gate's negative proof-of-fire get the k8 marker too.
_K8_NAMES = {"test_architecture_negative.py"}

# Integration / TCP / network tests are tagged slow for quick local runs.
_SLOW_NAMES = {
    "test_federated_tcp_execution.py",
    "test_net_agent_execution.py",
    "test_network_federation.py",
    "test_distributed_runtime.py",
    "test_distributed_runtime_tz015.py",
    "test_e2e_assembly.py",
    "test_cli_e2e.py",
}


def pytest_collection_modifyitems(items):
    import pytest as _pytest
    for item in items:
        parts = Path(str(item.path)).parts
        # find the tests/<sub> segment
        marker = None
        for i, seg in enumerate(parts):
            if seg == "tests" and i + 1 < len(parts):
                sub = parts[i + 1]
                marker = _SUBDIR_MARKER.get(sub)
                break
        if marker is None:
            continue
        item.add_marker(getattr(_pytest.mark, marker))
        if item.name and item.path.name in _K8_NAMES:
            item.add_marker(_pytest.mark.k8)
        if item.path.name in _SLOW_NAMES:
            item.add_marker(_pytest.mark.slow)
