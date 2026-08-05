"""Stage 7.2 - DependencyContainer (Composition Root) tests."""
import pytest

from infrastructure import DependencyContainer
from contracts import IFileSystem
from adapters import LocalFileSystemAdapter


def test_singleton_returns_same_object():
    c = DependencyContainer()
    c.register_factory("svc", lambda: object(), singleton=True)
    a = c.resolve("svc")
    b = c.resolve("svc")
    assert a is b


def test_transient_returns_distinct_objects_on_list():
    c = DependencyContainer()
    # use list (not int) to avoid small-int interning artifacts
    c.register_factory("lst", lambda: [], singleton=False)
    a = c.resolve("lst")
    b = c.resolve("lst")
    assert a is not b
    a.append(1)
    assert b == []  # isolation


def test_factory_called_per_resolve_when_factory_registered():
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return object()

    c = DependencyContainer()
    c.register_factory("f", factory, singleton=False)
    c.resolve("f")
    c.resolve("f")
    assert calls["n"] == 2


def test_resolve_unknown_key_raises_keyerror():
    c = DependencyContainer()
    with pytest.raises(KeyError):
        c.resolve("missing")


def test_register_factory_requires_callable():
    c = DependencyContainer()
    with pytest.raises(TypeError):
        c.register_factory("bad", 123, singleton=True)


def test_resolve_returns_interface_implementation():
    c = DependencyContainer()
    c.register_factory("IFileSystem", lambda: LocalFileSystemAdapter("."), singleton=True)
    fs = c.resolve("IFileSystem")
    assert isinstance(fs, IFileSystem)


def test_names_and_has():
    c = DependencyContainer()
    c.register_factory("a", lambda: 1)
    c.register_factory("b", lambda: 2)
    assert c.has("a") and c.has("b") and not c.has("z")
    assert set(c.names()) == {"a", "b"}


def test_register_instance_is_singleton():
    c = DependencyContainer()
    obj = object()
    c.register_instance("inst", obj)
    assert c.resolve("inst") is obj
