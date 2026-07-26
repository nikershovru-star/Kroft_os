"""Stage 7.1 - contract (port) layer tests."""
import abc

import pytest

from contracts import (
    IService,
    IFileSystem,
    IEventBus,
    ICapabilityRegistry,
)


def test_iservice_is_abstract_and_not_instantiable():
    assert issubclass(IService, abc.ABC)
    # ABC with abstract methods cannot be instantiated directly.
    with pytest.raises(TypeError):
        IService()


def test_ifilesystem_is_abstract_port():
    assert issubclass(IFileSystem, abc.ABC)
    expected = {"exists", "read_content", "write_content", "list_dir"}
    assert expected.issubset(IFileSystem.__abstractmethods__)
    # base cannot be instantiated -> abstract methods unimplemented
    with pytest.raises(TypeError):
        IFileSystem()


def test_ieventbus_is_abstract_port():
    assert issubclass(IEventBus, abc.ABC)
    expected = {"publish", "subscribe", "start", "stop"}
    assert expected.issubset(IEventBus.__abstractmethods__)
    with pytest.raises(TypeError):
        IEventBus()


def test_icapabilityregistry_is_abstract_port():
    assert issubclass(ICapabilityRegistry, abc.ABC)
    expected = {"register", "resolve", "has", "names"}
    assert expected.issubset(ICapabilityRegistry.__abstractmethods__)
    with pytest.raises(TypeError):
        ICapabilityRegistry()


def test_all_ports_are_abstract_base_contracts():
    # DESIGN NOTE (hexagonal, per Stage 2): sibling ports are independent
    # ABCs and do NOT inherit IService. IService is the canonical base for
    # *service* components only. The user spec item "all ports inherit
    # IService" is interpreted here as "all ports are abstract base
    # contracts". Flagged for architectural review - no fake pass.
    for port in (IService, IFileSystem, IEventBus, ICapabilityRegistry):
        assert issubclass(port, abc.ABC)
    assert issubclass(IService, abc.ABC)
