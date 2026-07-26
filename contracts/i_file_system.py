"""File-system port.

Decouples the kernel from any concrete I/O backend. Adapters implement
this against local disk, Vault, cloud storage, etc.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path


class IFileSystem(ABC):
    """Contract for all file system operations."""

    @abstractmethod
    def exists(self, absolute_path: "str | Path") -> bool: ...

    @abstractmethod
    def read_content(self, absolute_path: "str | Path") -> str: ...

    @abstractmethod
    def write_content(self, absolute_path: "str | Path", content: str) -> bool: ...

    @abstractmethod
    def list_dir(self, absolute_path: "str | Path") -> "list[str]": ...
