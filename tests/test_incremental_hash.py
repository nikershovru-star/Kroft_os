"""Stage 24 - Content-Hash Incremental Tracking tests (6).

CrawlStateTracker now stores sha256(content) alongside mtime so that
git-checkout/touch mtime bumps do NOT trigger a re-crawl if the hash is
unchanged. Legacy v1 state files (path -> mtime float) are migrated on load.

Adapted to the REAL tracker API (Stage 17):
  scan_mtimes(vault) -> Dict[relpath, mtime]
  get_changed_files(vault) -> (changed, deleted)   # reads state itself
  load_state() -> Dict[relpath, {"mtime": float, "hash": str|None}]
  save_state(Dict[relpath, mtime]) -> None          # hashes computed inside
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from adapters import LocalFileSystemAdapter
from services import CrawlStateTracker


@pytest.fixture
def tmp_vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "A.md").write_text("alpha", encoding="utf-8")
    (v / "B.md").write_text("beta", encoding="utf-8")
    return str(v)


def _tracker(vault: str):
    fs = LocalFileSystemAdapter(vault)
    return CrawlStateTracker(fs), fs


def test_hash_detects_real_change(tmp_vault):
    t, fs = _tracker(tmp_vault)
    t.save_state(t.scan_mtimes(tmp_vault))
    # Change content (mtime may or may not move — hash decides).
    Path(tmp_vault).joinpath("A.md").write_text("alpha CHANGED", encoding="utf-8")
    changed, deleted = t.get_changed_files(tmp_vault)
    assert "A.md" in changed
    assert "B.md" not in changed
    assert deleted == []


def test_hash_ignores_mtime_only_bump(tmp_vault):
    t, fs = _tracker(tmp_vault)
    t.save_state(t.scan_mtimes(tmp_vault))
    # Bump mtime WITHOUT changing content (git checkout / touch scenario).
    # +10s offset guarantees a different mtime on coarse filesystems.
    time.sleep(0.05)
    p = os.path.join(tmp_vault, "A.md")
    bumped = time.time() + 10.0
    os.utime(p, (bumped, bumped))
    changed, deleted = t.get_changed_files(tmp_vault)
    assert "A.md" not in changed  # hash unchanged -> not changed
    assert changed == []
    assert deleted == []


def test_new_file_detected_as_changed(tmp_vault):
    t, fs = _tracker(tmp_vault)
    t.save_state(t.scan_mtimes(tmp_vault))
    Path(tmp_vault).joinpath("C.md").write_text("gamma", encoding="utf-8")
    changed, deleted = t.get_changed_files(tmp_vault)
    assert "C.md" in changed
    assert "A.md" not in changed
    assert "B.md" not in changed
    assert deleted == []


def test_deleted_file_detected(tmp_vault):
    t, fs = _tracker(tmp_vault)
    t.save_state(t.scan_mtimes(tmp_vault))
    os.remove(os.path.join(tmp_vault, "A.md"))
    changed, deleted = t.get_changed_files(tmp_vault)
    assert "A.md" in deleted
    assert changed == []


def test_v1_state_migration(tmp_vault):
    t, fs = _tracker(tmp_vault)
    # Manually write a LEGACY v1 state file: {path: mtime}.
    v1 = {"A.md": 12345.0, "B.md": 12346.0}
    fs.write_content(".crawl_state.json", json.dumps(v1))
    st = t.load_state()
    # Migrated on load: hash=None -> per-file mtime fallback.
    assert st == {
        "A.md": {"mtime": 12345.0, "hash": None},
        "B.md": {"mtime": 12346.0, "hash": None},
    }
    # Real mtimes differ from 12345/12346 -> both fall back to mtime and
    # appear changed (v1 behavior preserved, zero regression).
    changed, deleted = t.get_changed_files(tmp_vault)
    assert sorted(changed) == ["A.md", "B.md"]
    assert deleted == []


def test_v2_state_roundtrip(tmp_vault):
    t, fs = _tracker(tmp_vault)
    t.save_state(t.scan_mtimes(tmp_vault))
    # Fresh tracker instance reloads v2 state -> nothing changed.
    t2, _ = _tracker(tmp_vault)
    t2._fs = fs  # same vault root; explicit for clarity
    changed, deleted = t2.get_changed_files(tmp_vault)
    assert changed == [] and deleted == []
    # Verify stored hashes are present and are sha256 hex.
    data = json.loads(fs.read_content(".crawl_state.json"))
    assert data["A.md"]["hash"] is not None
    assert len(data["A.md"]["hash"]) == 64  # sha256 hex digest
    assert isinstance(data["A.md"]["mtime"], float)
