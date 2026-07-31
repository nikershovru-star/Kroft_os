"""IMemoryStore / ISemanticMemory / IProceduralMemory — Memory Platform ports
(Wave 9, ADR-012).

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

Definition of Done (Roadmap Wave 9):

    Memory works independently of the concrete engine.

The five memory types (Working / Session / Long-Term / Semantic / Procedural)
are ROLES, not five storage interfaces: one `IMemoryStore` plus tags
(see `MemoryKind`) expresses them. Only roles with a genuinely different
operation shape get their own port — semantic search (by meaning, not key) and
procedural recall (execution patterns, Wave 10).

Thread-safety is NOT promised by this port (LAW 3: no hidden guarantees).
Implementations document their own behaviour; `InMemoryMemoryStore` happens to
lock, a future SQLite store may not need to.
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple


class MemoryKind:
    """Tag taxonomy for memory roles (ADR-012 §2.1). Immutable constants."""

    WORKING = "working"
    SESSION = "session"
    LONG_TERM = "long_term"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    CONSOLIDATED = "consolidated"

    ALL = (WORKING, SESSION, LONG_TERM, SEMANTIC, PROCEDURAL, CONSOLIDATED)


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MemoryItem:
    """One remembered thing. Immutable (LAW 3).

    `tags` and `embedding` are normalised to tuples in __post_init__: a frozen
    dataclass freezes the REFERENCE, not the container, so a plain list would
    still be mutable via .append() (pitfall carried over from Wave 8's Fact).
    """

    key: str
    content: str
    timestamp: float = 0.0
    ttl: Optional[int] = None            # seconds; None = never expires
    importance: float = 1.0              # 0.0-1.0, drives compression priority
    tags: Tuple[str, ...] = ()
    embedding: Optional[Tuple[float, ...]] = None   # Semantic Memory v1.0
    source: str = ""                     # provenance (LAW 4)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags or ()))
        if self.embedding is not None:
            object.__setattr__(self, "embedding", tuple(self.embedding))
        if not self.timestamp:
            object.__setattr__(self, "timestamp", time.time())

    # --- TTL ---------------------------------------------------------------
    def is_expired(self, now: Optional[float] = None) -> bool:
        """True when the item outlived its TTL (ADR-012 §3: lazy check)."""
        if self.ttl is None:
            return False
        moment = time.time() if now is None else now
        return moment > self.timestamp + self.ttl

    def age(self, now: Optional[float] = None) -> float:
        moment = time.time() if now is None else now
        return max(0.0, moment - self.timestamp)

    # --- immutable updates -------------------------------------------------
    def with_tags(self, *extra: str) -> "MemoryItem":
        """Return a NEW item with additional tags (no duplicates, order kept)."""
        merged = list(self.tags)
        for t in extra:
            if t not in merged:
                merged.append(t)
        return replace(self, tags=tuple(merged))

    def with_importance(self, importance: float) -> "MemoryItem":
        return replace(self, importance=float(importance))

    def has_tags(self, tags) -> bool:
        """True when the item carries EVERY tag in `tags` (AND semantics)."""
        return set(tags or ()).issubset(set(self.tags))


@dataclass
class MemoryQuery:
    """Retrieval criteria. Mutable by design — it is a short-lived request
    object, never shared state.

    All provided criteria combine with AND. `key_pattern` uses fnmatch globbing
    (`session:*`), NOT regex — stdlib-first and predictable for callers.
    """

    key_pattern: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    semantic_query: Optional[str] = None
    time_range: Optional[Tuple[float, float]] = None
    min_importance: Optional[float] = None
    limit: Optional[int] = None


@dataclass
class ConsolidationReport:
    """Outcome of a Session -> Long-Term consolidation (LAW 4/LAW 5).

    Not frozen: a local accumulator for one call, never shared.
    """

    session_key: str = ""
    examined: int = 0
    promoted: List[MemoryItem] = field(default_factory=list)
    skipped: List[MemoryItem] = field(default_factory=list)
    audit_log: List[str] = field(default_factory=list)

    @property
    def promotion_rate(self) -> float:
        if not self.examined:
            return 0.0
        return len(self.promoted) / float(self.examined)


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class IMemoryStore(abc.ABC):
    """Storage port for memory items.

    Engine-agnostic (ADR-012 DoD): in-memory (v0.1), SQLite (v0.5) and
    vector-store (v1.0) all sit behind this interface.

    NOTE: this port does NOT promise thread-safety. Implementations state their
    own guarantees.
    """

    @abc.abstractmethod
    def put(self, item: MemoryItem) -> None:
        """Store (or overwrite) an item by its key."""
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, key: str) -> Optional[MemoryItem]:
        """Return the item, or None when missing OR expired (lazy TTL)."""
        raise NotImplementedError

    @abc.abstractmethod
    def query(self, q: MemoryQuery) -> List[MemoryItem]:
        """Return non-expired items matching every provided criterion."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_expired(self) -> int:
        """Physically drop expired items. Returns how many were removed."""
        raise NotImplementedError

    @abc.abstractmethod
    def compress(self, threshold: float = 0.3) -> int:
        """Drop items with importance < threshold. Returns how many (LAW 5)."""
        raise NotImplementedError


class ISemanticMemory(abc.ABC):
    """Retrieval by meaning rather than by key.

    A separate port because the operation shape differs from IMemoryStore:
    free text in, ranked items out.
    """

    @abc.abstractmethod
    def search(self, text: str, limit: int = 5) -> List[MemoryItem]:
        """Return up to `limit` items most relevant to `text`."""
        raise NotImplementedError


class IProceduralMemory(abc.ABC):
    """'How to do it' — execution patterns rather than facts (Wave 10 input)."""

    @abc.abstractmethod
    def record_procedure(self, name: str, steps: List[str], success: bool) -> None:
        """Remember that `name` was executed as `steps` with a given outcome."""
        raise NotImplementedError

    @abc.abstractmethod
    def recall_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        """Return the best-known way to perform `name`, or None."""
        raise NotImplementedError
