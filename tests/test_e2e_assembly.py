"""Stage 7.6 - End-to-End assembly: container -> kernel -> real disk write."""
import os
import shutil

import pytest

from infrastructure import DependencyContainer
from kernel import Kernel, LifecycleState
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from contracts import IFileSystem, ICapabilityRegistry

from pathlib import Path


@pytest.fixture
def project_sandbox():
    base = Path(__file__).resolve().parent / ".e2e_sandbox"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


def test_e2e_kernel_writes_file_to_disk(project_sandbox):
    # 1. Container + registrations (composition root)
    container = DependencyContainer()
    registry = CapabilityRegistry()
    fs = LocalFileSystemAdapter(project_sandbox)
    container.register_instance("IFileSystem", fs)
    container.register_instance("ICapabilityRegistry", registry)

    # 2. Kernel + lifecycle
    kernel = Kernel(container)
    assert kernel.state == LifecycleState.UNINITIALIZED
    kernel.initialize()
    assert kernel.state == LifecycleState.INITIALIZED
    kernel.start()
    assert kernel.state == LifecycleState.RUNNING

    # 3. During RUNNING, resolve IFileSystem from container and write
    fs_resolved = container.resolve("IFileSystem")
    assert isinstance(fs_resolved, IFileSystem)
    assert fs_resolved.write_content("e2e.txt", "KROFT_OS v5 OK") is True

    # 4. File REALLY exists on disk at an absolute path
    abs_path = (project_sandbox / "e2e.txt").resolve()
    assert os.path.isabs(str(abs_path))
    assert os.path.exists(str(abs_path)) is True
    with open(str(abs_path), "r", encoding="utf-8") as fh:
        assert fh.read() == "KROFT_OS v5 OK"

    # 5. CapabilityRegistry in container is the SAME singleton the kernel uses
    assert kernel.wired["ICapabilityRegistry"] is registry
    assert container.resolve("ICapabilityRegistry") is registry
    assert isinstance(registry, ICapabilityRegistry)

    # 6. Stop
    kernel.stop()
    assert kernel.state == LifecycleState.STOPPED
