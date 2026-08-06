"""IApprovalGate — человеческий предохранитель для чувствительных действий (Phase C, Wave C6, ADR-103).

K5/K6-compliant: contracts + stdlib only. Переиспользует IActionLog (IDT-01) для audit.
НЕ дублирует IPolicy/PolicyContext/PolicyDecision (ADR-034/030) — они для model-selection;
ApprovalGate — отдельный boundary (человеческое одобрение действия агента).

Контракт (аудит #6 / ТЗ):
- request_approval НЕ блокирует event loop (решение принимает injected approver; рантайм
  сам по себе не ждёт human в синхронном пути);
- TTL + default-deny: если approver не вернул решение в ttl_sec -> denied (НЕ livelock
  ожидания одобрения);
- каждое решение аудитуется в IActionLog (append-only, non-bypassable).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ApprovalRequest:
    """Запрос на одобрение чувствительного действия агента."""

    action_id: str
    capability: str
    payload: str
    agent_id: str = "runtime"


@dataclass(frozen=True)
class ApprovalDecision:
    """Решение гейта (default-deny semantics: denied пока не approved)."""

    approved: bool
    reason: str
    timed_out: bool = False  # True если решение = default-deny по TTL


class IApprovalGate(ABC):
    """Человеческий предохранитель: чувствительные действия требуют одобрения."""

    @abstractmethod
    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Вернуть решение (approved/denied). Non-blocking; TTL -> default-deny.

        Каждое решение аудитируется в IActionLog вызывающей стороной (или самим gate).
        """
        raise NotImplementedError

    @abstractmethod
    def is_sensitive(self, capability: str) -> bool:
        """Входит ли capability в список чувствительных (требует гейта)."""
        raise NotImplementedError
