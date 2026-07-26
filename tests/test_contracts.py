"""Stage 7.1 - contract (port) layer tests."""
import abc

import pytest

from contracts import (
    IService,
    IFileSystem,
    IEventBus,
    ICapabilityRegistry,
    IGraphBuilder,
    IGraphQuery,
)


def test_iservice_is_abstract_and_not_instantiable():
    assert issubclass(IService, abc.ABC)
    with pytest.raises(TypeError):
        IService()


def test_ifilesystem_is_abstract_port():
    assert issubclass(IFileSystem, abc.ABC)
    expected = {"exists", "read_content", "write_content", "append", "delete", "rename", "list_dir"}
    assert expected.issubset(IFileSystem.__abstractmethods__)
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


def test_igraph_builder_is_service_port():
    # IGraphBuilder is a SERVICE-style port: it inherits IService.
    assert issubclass(IGraphBuilder, IService)
    assert issubclass(IGraphBuilder, abc.ABC)
    expected = {
        "add_node", "add_edge", "get_graph", "get_neighbors", "clear",
        "remove_node",
        "snapshot", "restore",
        "name", "initialize", "execute",
    }
    assert expected.issubset(IGraphBuilder.__abstractmethods__)
    with pytest.raises(TypeError):
        IGraphBuilder()


def test_igraph_query_is_service_port():
    # IGraphQuery is a SERVICE-style port: it inherits IService.
    assert issubclass(IGraphQuery, IService)
    assert issubclass(IGraphQuery, abc.ABC)
    expected = {
        "backlinks", "forward_links", "nodes_by_tag", "orphan_nodes",
        "path", "cluster_by_tag", "stats",
        "name", "initialize", "execute",
    }
    assert expected.issubset(IGraphQuery.__abstractmethods__)
    with pytest.raises(TypeError):
        IGraphQuery()


def test_all_ports_are_abstract_base_contracts():
    # Sibling ports are independent ABCs and do NOT inherit IService.
    sibling_ports = (IFileSystem, IEventBus, ICapabilityRegistry)
    for port in sibling_ports:
        assert issubclass(port, abc.ABC)
        assert not issubclass(port, IService)
    # Service-style ports DO inherit IService (IGraphBuilder, IGraphQuery, services).
    assert issubclass(IGraphBuilder, IService)
    assert issubclass(IGraphQuery, IService)
    assert issubclass(IGraphBuilder, abc.ABC)
    assert issubclass(IGraphQuery, abc.ABC)
    assert issubclass(IService, abc.ABC)
