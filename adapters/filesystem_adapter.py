"""Local filesystem adapter — concrete IFileSystem implementation.

Implements the file-system port against the local OS. All paths are
resolved relative to a configurable base directory and confined to it
(path-traversal guard).
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import List

from contracts import IFileSystem


class LocalFileSystemAdapter(IFileSystem):
    def __init__(self, base_dir: "str | Path") -> None:
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _safe(self, absolute_path: "str | Path") -> Path:
        p = (self._base / Path(absolute_path)).resolve()
        # Confine to base directory (prevent traversal escape).
        if self._base != p and self._base not in p.parents:
            raise ValueError(f"Path escapes base directory: {p}")
        return p

    def exists(self, absolute_path: "str | Path") -> bool:
        return self._safe(absolute_path).exists()

    def read_content(self, absolute_path: "str | Path") -> str:
        return self._safe(absolute_path).read_text(encoding="utf-8")

    def write_content(self, absolute_path: "str | Path", content: str) -> bool:
        target = self._safe(absolute_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True

    def append(self, absolute_path: "str | Path", content: str) -> bool:
        target = self._safe(absolute_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(content)
        return True

    def delete(self, absolute_path: "str | Path") -> bool:
        p = self._safe(absolute_path)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
        return True

    def list_dir(self, absolute_path: "str | Path") -> List[str]:
        d = self._safe(absolute_path)
        if not d.exists():
            return []
        return [str(p.relative_to(self._base)) for p in d.iterdir()]
