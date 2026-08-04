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
