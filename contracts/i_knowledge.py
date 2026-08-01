"""IKnowledgeGraph / IEntityExtractor / IValidator / IFactChecker — Knowledge
Platform ports (Wave 8, ADR-011).

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

Core rule of the platform (ADR-011 §2):

    LLM produces HYPOTHESES only. The Knowledge Graph accepts FACTS only.

Every Fact carries Decision -> Evidence -> Explanation (LAW 4): where it came
from (`source`), what backs it (`evidence`), how sure we are (`confidence`) and
what happened to it (`history`, append-only — LAW 3).
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field, replace
from typing import Any, List, Mapping, Optional, Tuple

from contracts.i_eval import Scorecard
from contracts.i_policy import PolicyContext


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Entity:
    """A named thing found in text. Immutable (LAW 3)."""
    name: str
    type: str = "concept"
    evidence: str = ""
    source: str = ""


@dataclass(frozen=True)
class Relation:
    """A subject-predicate-object triple, with no trust attached yet."""
    subject: str
    predicate: str
    object: str


@dataclass(frozen=True)
class Hypothesis:
    """An UNVERIFIED claim produced by an LLM (ADR-011 §2.2).

    A Hypothesis must never be written into the Knowledge Graph directly; it
    has to pass through an IValidator first.
    """
    subject: str
    predicate: str
    object: str
    source: str = ""          # model_id / document_id it came from
    evidence: str = ""        # raw chunk text / trace_id
    confidence: float = 0.0   # pre-validation guess (0.0 = unknown)

    def as_relation(self) -> Relation:
        return Relation(self.subject, self.predicate, self.object)

    def is_well_formed(self) -> bool:
        """v0.1 structural check: all three triple fields non-empty."""
        return bool(
            (self.subject or "").strip()
            and (self.predicate or "").strip()
            and (self.object or "").strip()
        )


@dataclass(frozen=True)
class Fact:
    """A VERIFIED claim — the only thing the Knowledge Graph stores.

    `history` is an append-only tuple of {timestamp, action, actor} records.
    A frozen dataclass with a *list* would still allow silent in-place mutation,
    so the container is normalised to a tuple in __post_init__ (LAW 3: no hidden
    mutable state). Mutation is expressed as a NEW object via `with_history()`.
    """
    subject: str
    predicate: str
    object: str
    source: str = ""                       # model_id / document_id
    evidence: str = ""                     # raw text / trace_id
    confidence: float = 0.0                # 0.0-1.0, from Evaluation
    history: Tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        # normalise any Sequence (list from a caller / JSON) into an immutable tuple
        object.__setattr__(
            self, "history", tuple(dict(h) for h in (self.history or ()))
        )

    # --- append-only history (returns a new Fact, never mutates) -----------
    def with_history(
        self,
        action: str,
        actor: str,
        timestamp: Optional[float] = None,
    ) -> "Fact":
        record = {
            "timestamp": time.time() if timestamp is None else timestamp,
            "action": action,
            "actor": actor,
        }
        return replace(self, history=self.history + (record,))

    def key(self) -> Tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)

    def as_relation(self) -> Relation:
        return Relation(self.subject, self.predicate, self.object)


@dataclass
class IngestReport:
    """Outcome of ingesting one document (observability, LAW 5).

    Not frozen: it is a mutable accumulator local to a single ingest call,
    never shared state.
    """
    document_id: str = ""
    chunks: int = 0
    hypotheses: int = 0
    accepted: List[Fact] = field(default_factory=list)
    rejected: List[Hypothesis] = field(default_factory=list)
    audit_log: List[str] = field(default_factory=list)

    @property
    def acceptance_rate(self) -> float:
        if not self.hypotheses:
            return 0.0
        return len(self.accepted) / float(self.hypotheses)


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class IEntityExtractor(abc.ABC):
    """Extracts entities and relation hypotheses from text via an LLM (Router).

    Implementations receive the router as an injected callable, never as a
    concrete Router class (LAW 2).
    """

    @abc.abstractmethod
    def extract(self, text: str, context: PolicyContext) -> List[Entity]:
        """Return entities mentioned in `text`."""
        raise NotImplementedError

    @abc.abstractmethod
    def extract_relations(self, text: str, context: PolicyContext) -> List[Hypothesis]:
        """Return relation HYPOTHESES (subject/predicate/object) found in `text`."""
        raise NotImplementedError


class IValidator(abc.ABC):
    """Turns a hypothesis into a Fact using Evaluation Platform evidence.

    v0.1: heuristic (well-formed triple + measured confidence >= floor).
    v1.0: rubric-based LLM judge (ADR-011 §3).
    """

    @abc.abstractmethod
    def validate(self, hypothesis: Hypothesis, scorecard: Optional[Scorecard]) -> Optional[Fact]:
        """Return a Fact when the hypothesis is verified, else None."""
        raise NotImplementedError


class IFactChecker(abc.ABC):
    """Scores a single hypothesis' trustworthiness (0.0-1.0)."""

    @abc.abstractmethod
    def check(self, hypothesis: Hypothesis, scorecard: Optional[Scorecard]) -> float:
        raise NotImplementedError


class IKnowledgeGraph(abc.ABC):
    """Storage port for VERIFIED knowledge. Accepts Facts only (ADR-011 §2)."""

    @abc.abstractmethod
    def add_fact(self, fact: Fact) -> bool:
        """Persist a Fact. Returns True if newly stored, False if already known."""
        raise NotImplementedError

    @abc.abstractmethod
    def facts(self) -> List[Fact]:
        """Return every stored Fact."""
        raise NotImplementedError

    @abc.abstractmethod
    def find(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
    ) -> List[Fact]:
        """Return Facts matching the given triple pattern (None = wildcard)."""
        raise NotImplementedError
