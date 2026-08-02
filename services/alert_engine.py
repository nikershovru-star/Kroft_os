"""Event-driven alert engine (TZ-OBS-001, ADR-040).

K8-compliant: services/ only, imports contracts + stdlib. K5: the engine ONLY
publishes `alert.{severity}` events and appends to an alerts log — it NEVER
performs recovery (that is the Supervisor's authority). K6: all input arrives
via the IEventBus; the engine does not import source modules directly.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from contracts import IEventBus
from contracts.i_telemetry import ITelemetrySink


class AlertEngine:
    """Subscribes to failure events, applies threshold rules, emits alerts."""

    # Default rules: (event_topic, metric_name, threshold, window_sec, severity)
    DEFAULT_RULES = [
        ("circuit.open", "circuit.trip", 5.0, 60.0, "critical"),
        ("sandbox.kill", "sandbox.kill", 3.0, 60.0, "warning"),
        ("agent.failure", "agent.failure", 5.0, 60.0, "critical"),
    ]

    def __init__(
        self,
        bus: IEventBus,
        sink: ITelemetrySink,
        alert_log_path: Optional[str] = None,
        rules: Optional[List[tuple]] = None,
        logger: Any = None,
    ) -> None:
        self._bus = bus
        self._sink = sink
        self._log_path = alert_log_path
        self._rules = rules or list(self.DEFAULT_RULES)
        self._log = logger
        self._lock = threading.Lock()
        # K6: subscribe to exact EventBus topics; closures carry the topic name.
        bus.subscribe("circuit.open", lambda e: self._on_event("circuit.open", e))
        bus.subscribe("sandbox.kill", lambda e: self._on_event("sandbox.kill", e))
        bus.subscribe("agent.failure", lambda e: self._on_event("agent.failure", e))
        bus.subscribe("degradation.level", self._on_degradation)
        bus.subscribe("self.drift", self._on_drift)

    # --- handlers ---------------------------------------------------------

    def _on_event(self, topic: str, event: dict) -> None:
        metric = self._metric_for_topic(topic)
        if metric is None:
            return
        self._sink.record(metric, 1.0, tags={"source": str(event.get("agent_id", event.get("component", "unknown")))})
        self._evaluate(topic, metric)

    def _on_degradation(self, event: dict) -> None:
        level = event.get("level", "")
        self._sink.record("degradation.level", 1.0, tags={"level": level})
        if level == "MINIMAL":
            self._emit("critical", "degradation reached MINIMAL", event)
        elif level == "PARTIAL":
            self._emit("warning", "degradation reached PARTIAL", event)

    def _on_drift(self, event: dict) -> None:
        score = float(event.get("score", 0.0))
        self._sink.record("drift.score", score, tags={"file": str(event.get("file", ""))})
        if score > 0.8:
            self._emit("warning", f"architecture drift score {score:.2f} > 0.8", event)

    # --- rule evaluation --------------------------------------------------

    def _evaluate(self, topic: str, metric: str) -> None:
        for rule_topic, rule_metric, threshold, window, severity in self._rules:
            if rule_topic != topic or rule_metric != metric:
                continue
            agg = self._sink.aggregate(metric, window)
            if agg["count"] >= threshold:
                self._emit(severity, f"{metric} rate {agg['count']:.0f}/{window:.0f}s >= {threshold:.0f}", {"topic": topic})

    # --- emit -------------------------------------------------------------

    def _emit(self, severity: str, message: str, context: dict) -> None:
        alert = {
            "severity": severity,
            "message": message,
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._bus.publish_sync(f"alert.{severity}", alert)
        self._append_log(alert)
        if self._log:
            self._log.warn(f"alert.{severity}", message=message)

    def _append_log(self, alert: dict) -> None:
        if not self._log_path:
            return
        with self._lock:
            os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(alert, ensure_ascii=False) + "\n")

    # --- helpers ----------------------------------------------------------

    @staticmethod
    def _metric_for_topic(topic: str) -> Optional[str]:
        return {
            "circuit.open": "circuit.trip",
            "sandbox.kill": "sandbox.kill",
            "agent.failure": "agent.failure",
        }.get(topic)
