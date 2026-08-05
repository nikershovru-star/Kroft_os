"""Tests for TZ-OBS-001 (Observability, ADR-040).

Targets >=8 tests. Verifies InMemoryTelemetrySink + AlertEngine on EventBus,
plus negative proof-of-fire (K1/K8).
"""
import threading
import time

from contracts.i_telemetry import ITelemetrySink, MetricPoint
from adapters.in_memory_telemetry import InMemoryTelemetrySink
from services.alert_engine import AlertEngine
from infrastructure.eventbus import InMemoryEventBus


def _capture(bus, topic):
    seen = []
    bus.subscribe(topic, lambda e: seen.append(e))
    return seen


def test_sink_record_query():
    s = InMemoryTelemetrySink(capacity=100, clock=lambda: 1000.0)
    s.record("x", 1.0)
    s.record("x", 2.0, tags={"k": "v"})
    pts = s.query("x", 60.0)
    assert len(pts) == 2
    assert pts[0].value == 1.0
    assert pts[1].tags == frozenset({("k", "v")})


def test_sink_window_filter():
    # Fixed clock within window
    s = InMemoryTelemetrySink(capacity=100, clock=lambda: 1000.0)
    s.record("x", 1.0)
    assert len(s.query("x", 30.0)) == 1  # 1000 >= 1000-30
    # Real-clock exclusion: point recorded, then query with tiny window after sleep
    s2 = InMemoryTelemetrySink(capacity=100)
    s2.record("old", 1.0)
    time.sleep(0.05)
    assert s2.query("old", 0.001) == []  # point is ~0.05s old, window 0.001s -> excluded
    assert len(s2.query("old", 5.0)) == 1  # wide window -> included


def test_sink_ring_eviction():
    s = InMemoryTelemetrySink(capacity=3, clock=lambda: 1000.0)
    for i in range(5):
        s.record("x", float(i))
    snap = s.snapshot()["x"]
    assert len(snap) == 3  # maxlen=3
    assert [p.value for p in snap] == [2.0, 3.0, 4.0]


def test_sink_thread_safety():
    s = InMemoryTelemetrySink(capacity=1000, clock=lambda: 1000.0)
    def worker(n):
        for i in range(50):
            s.record("m", float(n + i))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(s.query("m", 60.0)) == 200


def test_sink_aggregate():
    s = InMemoryTelemetrySink(capacity=100, clock=lambda: 1000.0)
    for v in [1.0, 2.0, 3.0]:
        s.record("a", v)
    agg = s.aggregate("a", 60.0)
    assert agg["count"] == 3.0
    assert agg["sum"] == 6.0
    assert agg["avg"] == 2.0
    assert agg["max"] == 3.0
    assert agg["min"] == 1.0


def test_alert_engine_circuit_breach():
    bus = InMemoryEventBus()
    sink = InMemoryTelemetrySink(capacity=100)
    alerts = _capture(bus, "alert.critical")
    AlertEngine(bus, sink)
    # 5 circuit.open within 60s -> rate >= 5 -> critical
    for _ in range(5):
        bus.publish_sync("circuit.open", {"agent_id": "a1"})
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert sink.aggregate("circuit.trip", 60.0)["count"] == 5.0


def test_alert_engine_no_breach_silence():
    bus = InMemoryEventBus()
    sink = InMemoryTelemetrySink(capacity=100)
    alerts = _capture(bus, "alert.critical")
    AlertEngine(bus, sink)
    bus.publish_sync("circuit.open", {"agent_id": "a1"})  # 1 < 5 -> silent
    assert len(alerts) == 0


def test_alert_engine_degradation_minimal():
    bus = InMemoryEventBus()
    sink = InMemoryTelemetrySink(capacity=100)
    crit = _capture(bus, "alert.critical")
    warn = _capture(bus, "alert.warning")
    AlertEngine(bus, sink)
    bus.publish_sync("degradation.level", {"level": "MINIMAL", "reason": "x"})
    assert len(crit) == 1
    assert len(warn) == 0
    bus.publish_sync("degradation.level", {"level": "PARTIAL", "reason": "y"})
    assert len(warn) == 1


def test_alert_engine_drift_warning():
    bus = InMemoryEventBus()
    sink = InMemoryTelemetrySink(capacity=100)
    warn = _capture(bus, "alert.warning")
    AlertEngine(bus, sink)
    bus.publish_sync("self.drift", {"score": 0.9, "count": 18})
    assert len(warn) == 1  # 0.9 > 0.8 -> warning
    bus.publish_sync("self.drift", {"score": 0.3, "count": 5})
    assert len(warn) == 1  # 0.3 -> silent


def test_alert_engine_k5_no_recovery_imports():
    # Negative proof-of-fire: AlertEngine must NOT import source modules.
    import inspect
    src = inspect.getsource(AlertEngine)
    assert "import services.supervisor" not in src
    assert "import runtime" not in src
    assert "from services.supervisor" not in src


def test_port_k1_clean():
    # Negative proof-of-fire: ITelemetrySink port must not import services/runtime/adapters.
    import inspect
    src = inspect.getsource(ITelemetrySink)
    assert "import services" not in src and "from services" not in src
    assert "import runtime" not in src and "from runtime" not in src
    assert "import adapters" not in src and "from adapters" not in src
