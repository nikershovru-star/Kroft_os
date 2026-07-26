"""Stage 8 - EventBus <-> Kernel integration tests."""
import pytest

from infrastructure import DependencyContainer, InMemoryEventBus
from kernel import Kernel, LifecycleState
from contracts import IEventBus


def test_kernel_emits_lifecycle_events():
    container = DependencyContainer()
    bus = InMemoryEventBus()
    container.register_instance("IEventBus", bus)
    k = Kernel(container)
    k.initialize()
    k.start()
    k.stop()
    types = [e["type"] for e in bus.get_history("kernel.lifecycle")]
    assert types == ["kernel.started", "kernel.stopped"]
    assert k.state == LifecycleState.STOPPED


def test_container_wires_eventbus():
    container = DependencyContainer()
    container.register_factory("IEventBus", InMemoryEventBus, singleton=True)
    resolved = container.resolve("IEventBus")
    assert isinstance(resolved, IEventBus)
    assert isinstance(resolved, InMemoryEventBus)


def test_eventbus_is_singleton_in_container():
    container = DependencyContainer()
    container.register_factory("IEventBus", InMemoryEventBus, singleton=True)
    a = container.resolve("IEventBus")
    b = container.resolve("IEventBus")
    assert a is b


def test_arch_gate_eventbus_keeps_axis():
    # infrastructure/eventbus.py must NOT import kernel/runtime/adapters.
    # It may import contracts and any stdlib module (incl. __future__).
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
    assert not violations, f"EventBus axis violation: {violations}"
