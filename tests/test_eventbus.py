"""Stage 8 - InMemoryEventBus unit tests."""
import asyncio

import pytest

from infrastructure import InMemoryEventBus
from contracts import IEventBus


def test_subscribe_publish():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe("topic.a", lambda e: received.append(e))
    bus.publish_sync("topic.a", {"type": "x", "v": 1})
    assert len(received) == 1
    assert received[0]["v"] == 1


def test_async_handler():
    bus = InMemoryEventBus()
    received = []

    async def handler(e):
        received.append(e)

    bus.subscribe("topic.b", handler)

    async def run():
        await bus.publish("topic.b", {"type": "y"})

    asyncio.run(run())
    assert len(received) == 1
    assert received[0]["type"] == "y"


def test_multiple_subscribers():
    bus = InMemoryEventBus()
    hits = []

    def mk(i):
        def h(e):
            hits.append(i)
        return h

    for i in range(5):
        bus.subscribe("topic.m", mk(i))
    bus.publish_sync("topic.m", {"type": "m"})
    assert sorted(hits) == [0, 1, 2, 3, 4]


def test_handler_exception_isolation():
    calls = []

    def good(e):
        calls.append("good")

    def bad(e):
        raise RuntimeError("boom")

    bus = InMemoryEventBus()
    bus.subscribe("topic.e", good)
    bus.subscribe("topic.e", bad)
    bus.subscribe("topic.e", good)
    bus.publish_sync("topic.e", {"type": "e"})
    # good handler ran twice despite bad failing
    assert calls == ["good", "good"]


def test_event_log():
    bus = InMemoryEventBus()
    bus.publish_sync("topic.l", {"type": "one"})
    bus.publish_sync("topic.l", {"type": "two"})
    history = bus.get_history("topic.l")
    assert len(history) == 2
    assert history[0]["type"] == "one"
    assert history[1]["type"] == "two"


def test_clear_history():
    bus = InMemoryEventBus()
    bus.publish_sync("topic.c", {"type": "c"})
    assert len(bus.get_history()) == 1
    bus.clear_history()
    assert bus.get_history() == []


def test_publish_sync_noop_safe():
    bus = InMemoryEventBus()
    # must not raise
    bus.publish_sync("topic.s", {"type": "s"})
    assert bus.get_history("topic.s")[0]["type"] == "s"


def test_no_subscribers_noop():
    bus = InMemoryEventBus()
    # publishing with no subscribers must not raise
    bus.publish_sync("topic.none", {"type": "n"})
    assert bus.get_history("topic.none")[0]["type"] == "n"


def test_implements_port():
    assert isinstance(InMemoryEventBus(), IEventBus)
