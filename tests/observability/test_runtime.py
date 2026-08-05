"""Stage 7.4 - Runtime Context & Capability Registry tests."""
import pytest

from runtime import RuntimeContext, CapabilityRegistry
from contracts import ICapabilityRegistry


def test_capability_register_and_resolve():
    reg = CapabilityRegistry()
    handler = object()
    reg.register("cap.x", handler)
    assert reg.resolve("cap.x") is handler


def test_capability_resolve_unknown_raises_keyerror():
    reg = CapabilityRegistry()
    with pytest.raises(KeyError):
        reg.resolve("cap.unknown")


def test_capability_registry_isinstance_port():
    reg = CapabilityRegistry()
    assert isinstance(reg, ICapabilityRegistry)


def test_capability_names_and_has():
    reg = CapabilityRegistry()
    reg.register("a", 1)
    reg.register("b", 2)
    assert reg.has("a") and not reg.has("z")
    assert set(reg.names()) == {"a", "b"}


def test_runtime_context_stores_state():
    ctx = RuntimeContext()
    ctx.set("mode", "prod")
    ctx.set("counter", 42)
    assert ctx.get("mode") == "prod"
    assert ctx.get("counter") == 42
    assert ctx.get("missing", "default") == "default"


def test_runtime_context_carries_capability_registry():
    ctx = RuntimeContext()
    reg = CapabilityRegistry()
    ctx.capabilities = reg
    reg.register("cap.y", "impl")
    assert ctx.capability_names == ["cap.y"]


def test_runtime_context_state_isolation_between_instances():
    # Separate contexts keep separate state (no shared globals).
    a = RuntimeContext()
    b = RuntimeContext()
    a.set("k", 1)
    b.set("k", 2)
    assert a.get("k") == 1
    assert b.get("k") == 2


# NOTE on thread-safety (per spec 7.4 + limits 7.8):
# RuntimeContext/CapabilityRegistry rely on CPython GIL for atomic single
# dict operations but ship NO explicit lock. They are NOT proven safe under
# concurrent read/write load. This is a documented limitation, not a test gap
# we fake-pass. The test below asserts single-threaded correctness only.
def test_runtime_context_single_thread_correctness():
    ctx = RuntimeContext()
    for i in range(100):
        ctx.set(f"k{i}", i)
    assert len(ctx.state) == 100
    assert ctx.get("k50") == 50
