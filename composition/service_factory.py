"""composition/service_factory.py — Service assembly facade (Phase B.1).

Тонкий фасад над container_builder._wire_agent / _wire_scheduler. Реальная
регистрация сервисов (VaultStreamCrawler, GraphQueryEngine, AgentService, ...)
живёт в container_builder.build_container — единственной точке сборки. Этот
модуль — точка расширения для будущих сервисов (Multi-Agent, Knowledge Platform).
"""
from __future__ import annotations

from composition.container_builder import _wire_agent, _wire_scheduler


def wire_agent(container) -> None:
    """Register agent tools + return AgentService (delegates to container_builder)."""
    return _wire_agent(container)


def wire_scheduler(container) -> None:
    """Wire scheduler executor to agent (delegates to container_builder)."""
    _wire_scheduler(container)
