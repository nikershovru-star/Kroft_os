"""Stage 7.5 - LocalFileSystemAdapter (IFileSystem) tests."""
import shutil

import pytest

from adapters import LocalFileSystemAdapter
from contracts import IFileSystem

import tempfile
from pathlib import Path


@pytest.fixture
def fs_adapter():
    # temporary directory INSIDE the project tree; cleaned up after test.
    base = Path(__file__).resolve().parent / ".sandbox"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
    adapter = LocalFileSystemAdapter(base)
    yield adapter
    shutil.rmtree(base, ignore_errors=True)


def test_adapter_implements_ifilesystem(fs_adapter):
    assert isinstance(fs_adapter, IFileSystem)


def test_write_then_read_roundtrip(fs_adapter):
    ok = fs_adapter.write_content("doc/note.md", "KnowledgeOS v5 OK")
    assert ok is True
    assert fs_adapter.read_content("doc/note.md") == "KnowledgeOS v5 OK"


def test_exists_after_write_and_delete(fs_adapter):
    fs_adapter.write_content("f.txt", "x")
    assert fs_adapter.exists("f.txt") is True
    (fs_adapter._base / "f.txt").unlink()
    assert fs_adapter.exists("f.txt") is False


def test_list_returns_files(fs_adapter):
    fs_adapter.write_content("a.txt", "1")
    fs_adapter.write_content("sub/b.txt", "2")
    listing = fs_adapter.list_dir(".")
    assert "a.txt" in listing
    assert "sub" in listing


def test_path_traversal_read_blocked(fs_adapter):
    # Attempt to escape the base directory must raise ValueError.
    with pytest.raises(ValueError):
        fs_adapter.read_content("../outside.txt")


def test_path_traversal_write_blocked(fs_adapter):
    with pytest.raises(ValueError):
        fs_adapter.write_content("../../escape.txt", "x")
