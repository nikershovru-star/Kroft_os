"""Approval Manager — human-in-loop gate (TZ-SEC-001 WP-08, ADR-034).

K1-compliant: imports ONLY contracts (stdlib). Async-safe in-memory store;
the human decision arrives via decide(). wait() returns immediately if
timeout=0 (non-blocking) so the kernel is never blocked.
"""
from __future__ import annotations

import threading
import uuid
from typing import Dict

from contracts.security import (
    ApprovalRequest,
    ApprovalStatus,
    IApprovalManager,
)


class ApprovalManager(IApprovalManager):
    def __init__(self) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}
        self._events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def request(self, agent_id: str, action: str, arguments: str) -> ApprovalRequest:
        req_id = uuid.uuid4().hex[:12]
        req = ApprovalRequest(agent_id=agent_id, action=action, arguments=arguments)
        with self._lock:
            self._requests[req_id] = req
            self._events[req_id] = threading.Event()
        req._id = req_id  # type: ignore[attr-defined]
        return req

    def decide(self, request_id: str, approve: bool, reason: str = "") -> ApprovalRequest:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise KeyError(f"unknown approval request {request_id}")
            req.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.DENIED
            req.decision_reason = reason
            self._events[request_id].set()
        return req

    def wait(self, request_id: str, timeout: float = 0.0) -> ApprovalRequest:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise KeyError(f"unknown approval request {request_id}")
            event = self._events[request_id]
        if timeout == 0.0:
            return req  # non-blocking: caller polls status later
        event.wait(timeout)
        return self._requests[request_id]

    def status(self, request_id: str) -> ApprovalStatus:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise KeyError(f"unknown approval request {request_id}")
            return req.status
