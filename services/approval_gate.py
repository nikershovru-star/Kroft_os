"""ApprovalGate — человеческий предохранитель для чувствительных действий (Wave C6).

K1/K6: services импортирует только contracts + stdlib. Переиспользует IActionLog (IDT-01)
для audit (НЕ дублирует). IApprovalGate интерфейс.

Non-blocking (аудит #6 / ТЗ): request_approval запускает injected approver в executor с
timeout=ttl_sec; по таймауту -> default-deny (timed_out=True), НЕ livelock ожидания.
Каждое решение аудитируется в IActionLog.append (append-only, non-bypassable).
"""

from __future__ import annotations

import concurrent.futures
from typing import Callable, Optional, Set

from contracts.i_approval_gate import ApprovalDecision, ApprovalRequest, IApprovalGate
from contracts.i_identity import IActionLog


class ApprovalGate(IApprovalGate):
    """Async approval с TTL + default-deny + audit."""

    def __init__(
        self,
        approver: Callable[[ApprovalRequest], bool],
        action_log: IActionLog,
        sensitive_capabilities: Optional[Set[str]] = None,
        ttl_sec: float = 5.0,
    ) -> None:
        self._approver = approver
        self._log = action_log
        self._sensitive = sensitive_capabilities or set()
        self._ttl = ttl_sec

    def is_sensitive(self, capability: str) -> bool:
        return capability in self._sensitive

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        # Non-blocking: approver в executor с таймаутом; таймаут -> default-deny.
        # НЕ ждём завершения фонового потока (shutdown(wait=False)), чтобы event loop
        # не блокировался на slow approver (напр. ожидание human).
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = ex.submit(self._approver, request)
            try:
                approved = fut.result(timeout=self._ttl)
                reason = "approved" if approved else "denied by approver"
                timed_out = False
            except concurrent.futures.TimeoutError:
                approved = False
                reason = f"default-deny: approval timed out after {self._ttl}s"
                timed_out = True
            except Exception as exc:  # любой сбой approver -> deny (fail-closed)
                approved = False
                reason = f"default-deny: approver error ({exc})"
                timed_out = False
        finally:
            ex.shutdown(wait=False)
        # audit (non-bypassable, append-only)
        self._log.append(
            request.agent_id,
            f"approval {request.action_id} cap={request.capability}: "
            f"{'APPROVED' if approved else 'DENIED'} ({reason})",
        )
        return ApprovalDecision(approved=approved, reason=reason, timed_out=timed_out)
