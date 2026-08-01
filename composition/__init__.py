"""composition/ — Composition Root (ADR-026, Phase B).

ВНИМАНИЕ: это СКЕЛЕТ слоя. Реальная логика переносится сюда поэтапно
ПОСЛЕ утверждения Dependency Report (LAW K5: Humans Approve). См.
`docs/architecture/Dependency Report — Phase B.md` и ADR-026/027/028.

Ответственность Composition Root (ЕДИНСТВЕННОЕ место создания/связывания):
  - DependencyContainer        (из infrastructure)
  - SnapshotRepository         (impl ISnapshotRepository, wrap infrastructure.SnapshotStore)
  - EventBus                   (InMemoryEventBus)
  - Services                   (VaultStreamCrawler, GraphQueryEngine, ...)
  - Adapters                   (LocalFileSystemAdapter, ...)
  - PluginManager / Configuration / Logger

Kernel НЕ создаёт ничего из перечисленного — получает готовым через конструктор
(только ports из contracts). Kernel imports: {contracts, runtime, stdlib}.
"""

__all__ = []
