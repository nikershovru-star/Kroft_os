"""Stage 7.3 - Kernel lifecycle FSM tests."""
import tempfile

import pytest

from kernel import Kernel, LifecycleState
from infrastructure import DependencyContainer
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter


def test_uninitialized_to_initialized():
    k = Kernel()
    assert k.state == LifecycleState.UNINITIALIZED
    k.initialize()
    assert k.state == LifecycleState.INITIALIZED


def test_initialized_to_running():
    k = Kernel()
    k.initialize()
    k.start()
    assert k.state == LifecycleState.RUNNING


def test_running_to_stopped():
    k = Kernel()
    k.initialize()
    k.start()
    k.stop()
    assert k.state == LifecycleState.STOPPED


def test_invalid_uninitialized_start_raises():
    k = Kernel()
    with pytest.raises(RuntimeError):
        k.start()


def test_invalid_running_initialize_raises():
    k = Kernel()
    k.initialize()
    k.start()
    with pytest.raises(RuntimeError):
        k.initialize()


def test_invalid_stopped_start_raises():
    k = Kernel()
    k.initialize()
    k.start()
    k.stop()
    with pytest.raises(RuntimeError):
        k.start()


def test_initialize_resolves_deps_from_container():
    # Honest injection test using real implementations in a container
    # (no 3rd-party mock lib; container is the seam).
    container = DependencyContainer()
    reg = CapabilityRegistry()
    tmp = tempfile.mkdtemp()
    fs = LocalFileSystemAdapter(tmp)
    container.register_instance("ICapabilityRegistry", reg)
    container.register_instance("IFileSystem", fs)

    k = Kernel(container)
    k.initialize()

    assert "ICapabilityRegistry" in k.wired
    assert "IFileSystem" in k.wired
    # The resolved objects are exactly the registered singletons.
    assert k.wired["ICapabilityRegistry"] is reg
    assert k.wired["IFileSystem"] is fs
    # RuntimeContext adopted the resolved registry.
    assert k.runtime_context is not None
    assert k.runtime_context.capabilities is reg
    assert k.state == LifecycleState.INITIALIZED
