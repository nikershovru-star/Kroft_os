"""PHASE 1 — KroftRuntime lifecycle tests (mock-based, fast).

These tests verify the Runtime orchestration contract WITHOUT loading the
750MB production foundation snapshot (ТЗ §11 regression: never touch the
production snapshot). Heavy collaborators (build_container / build_kernel /
KROFT_OSServer) are mocked so we assert lifecycle behaviour only:

  1. runtime starts
  2. runtime health = ready
  3. runtime stops
  4. stop is idempotent
  5. start -> stop -> start
  6. independent storage configuration (per-node RuntimeConfig)
  7. HTTP server attached
  8. existing KROFT functionality remains available (delegated, not duplicated)
 10. no duplicate container/kernel creation
 11. two Runtime instances can coexist (A != B by port/storage)

The real-foundation load is covered separately under tests/runtime/
test_runtime_foundation.py (marked slow) so the default suite stays fast.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make the repo root importable under the spaced Windows path.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.kroft_runtime import KroftRuntime, RuntimeConfig  # noqa: E402


@pytest.fixture
def patched(monkeypatch):
    """Inject lightweight fakes for the heavy collaborators (DI, not import)."""
    kernel = MagicMock(name="kernel")

    def fake_build_container(vault):
        # Return a FRESH container per call so the runtime never leaks a shared
        # mutable singleton across start/stop/start (ТЗ STEP 10.10).
        c = MagicMock(name="container")
        c.resolve.return_value = MagicMock(name="engine")
        c._vault = vault
        return c

    def fake_build_kernel(bus, cont):
        return kernel

    def fake_server_class(cont, host, port):
        s = MagicMock(name="KROFT_OSServer")
        s.port = port
        s._host = host
        s._port = port
        return s

    return fake_build_container, fake_build_kernel, fake_server_class


def _make(fake_build_container, fake_build_kernel, fake_server_class, **kw):
    cfg = RuntimeConfig(node_id=kw.pop("node_id", "kroft-a"),
                        api_port=kw.pop("api_port", 8101),
                        vault=kw.pop("vault", "./nodes/kroft-a"),
                        **kw)
    return KroftRuntime(
        cfg,
        build_container=fake_build_container,
        build_kernel=fake_build_kernel,
        server_factory=fake_server_class,
    )


def test_runtime_starts(patched):
    b = patched
    rt = _make(*b, node_id="kroft-a", api_port=8101, vault="./nodes/kroft-a")
    rt.start()
    assert rt.is_running is True
    assert rt.container is not None
    assert rt.kernel is not None
    assert rt.server is not None


def test_runtime_health_ready(patched):
    b = patched
    rt = _make(*b, node_id="kroft-a", api_port=8101)
    rt.start()
    h = rt.health()
    assert h["status"] == "ok"
    assert h["runtime"] == "running"
    assert h["kernel"] == "ready"
    assert h["http"] == "ready"
    assert h["node_id"] == "kroft-a"


def test_runtime_stops(patched):
    b = patched
    rt = _make(*b, api_port=8101)
    rt.start()
    rt.stop()
    assert rt.is_running is False
    # After stop, health reports down and no dangling references.
    assert rt.health()["status"] == "down"
    assert rt.container is None
    assert rt.kernel is None
    assert rt.server is None


def test_stop_is_idempotent(patched):
    b = patched
    rt = _make(*b, api_port=8101)
    rt.start()
    rt.stop()
    rt.stop()  # second call must not raise
    assert rt.is_running is False


def test_start_stop_start(patched):
    b = patched
    rt = _make(*b, api_port=8101)
    rt.start()
    assert rt.is_running
    rt.stop()
    assert not rt.is_running
    rt.start()
    assert rt.is_running
    rt.stop()


def test_independent_storage_configuration():
    cfg_a = RuntimeConfig(node_id="kroft-a", vault="./nodes/kroft-a", api_port=8101)
    cfg_b = RuntimeConfig(node_id="kroft-b", vault="./nodes/kroft-b", api_port=8102)
    assert cfg_a.vault != cfg_b.vault
    assert cfg_a.node_id != cfg_b.node_id
    assert cfg_a.api_port != cfg_b.api_port


def test_http_server_attached(patched):
    b = patched
    rt = _make(*b, api_port=8101)
    rt.start()
    srv = rt.server  # capture before stop() nulls the reference
    # server.start() was called exactly once by the runtime.
    assert srv.start.call_count == 1
    assert srv.port == 8101
    rt.stop()
    assert srv.stop.call_count == 1


def test_existing_functionality_delegated_not_duplicated(patched):
    b = patched
    rt = _make(*b, api_port=8101)
    rt.start()
    # Runtime must NOT invent its own search/query — it exposes the container
    # so external clients reach existing services through it.
    engine = rt.container.resolve("GraphQueryEngine")
    assert engine is not None
    rt.stop()


def test_no_duplicate_container_per_start(patched):
    b = patched
    rt = _make(*b, api_port=8101)
    rt.start()
    first_container = rt.container
    rt.stop()
    rt.start()
    # Each start builds a fresh container (no shared mutable singleton leaked).
    assert rt.container is not None
    assert rt.container is not first_container


def test_two_runtimes_coexist_independent(patched):
    b = patched
    rt_a = _make(*b, node_id="kroft-a", vault="./nodes/kroft-a", api_port=8101)
    rt_b = _make(*b, node_id="kroft-b", vault="./nodes/kroft-b", api_port=8102)
    rt_a.start()
    rt_b.start()
    # Distinct instances by identity / port / storage.
    assert rt_a.config.node_id != rt_b.config.node_id
    assert rt_a.config.api_port != rt_b.config.api_port
    assert rt_a.config.vault != rt_b.config.vault
    assert rt_a.is_running and rt_b.is_running
    rt_a.stop()
    rt_b.stop()
    assert not rt_a.is_running and not rt_b.is_running


def test_health_down_before_start():
    rt = KroftRuntime(RuntimeConfig(api_port=8101))
    h = rt.health()
    assert h["status"] == "down"
    assert h["runtime"] == "stopped"
