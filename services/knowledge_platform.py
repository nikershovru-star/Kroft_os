"""KnowledgePlatform — Wave 8 orchestrator (ADR-011 Phase D).

Pipeline (ADR-011 §2.1):

    Document -> Chunk -> Entity Extraction -> Relation Discovery
             -> Evidence -> Validation -> Knowledge Graph

Hard rule (ADR-011 §2): the LLM produces HYPOTHESES; only VERIFIED facts reach
the graph. The threshold check in `ingest()` is the single place where a model's
opinion becomes the system's knowledge.

Dependency rule (LAW 2): this module imports ONLY `contracts`. The extractor,
the validator and the graph arrive as PORTS (IEntityExtractor / IValidator /
IKnowledgeGraph); a router, if any, is already baked into the extractor adapter.
Service modules must not import sibling services either (arch gate), so the
default heuristic validator lives here rather than in another service module.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from contracts.i_eval import Scorecard
from contracts.i_knowledge import (
    Fact,
    Hypothesis,
    IEntityExtractor,
    IFactChecker,
    IKnowledgeGraph,
    IValidator,
    IngestReport,
)
from contracts.i_policy import PolicyContext
from contracts.i_llm import ModelQuery

# A scorer turns a hypothesis into Evaluation evidence. Injected as a callable
# (structural port) so the platform never depends on the Evaluation service.
ScorerFn = Callable[[Hypothesis], Optional[Scorecard]]

ACCURACY_METRIC = "accuracy"


# --------------------------------------------------------------------------
# Fact checking / validation (v0.1 heuristic — ADR-011 §3)
# --------------------------------------------------------------------------
class HeuristicFactChecker(IFactChecker):
    """Confidence from measurement when available, structure otherwise.

    v0.1 rule:
      - Scorecard present  -> confidence = metrics["accuracy"] (measured, LAW 5)
      - no Scorecard       -> structural prior for a well-formed triple
      - malformed triple   -> 0.0
    v1.0 replaces this with a rubric-based LLM judge.
    """

    def __init__(self, structural_prior: float = 0.8) -> None:
        self.structural_prior = structural_prior

    def check(self, hypothesis: Hypothesis, scorecard: Optional[Scorecard]) -> float:
        if not hypothesis.is_well_formed():
            return 0.0
        if scorecard is not None:
            return float(scorecard.metrics.get(ACCURACY_METRIC, 0.0))
        return float(self.structural_prior)


class HeuristicValidator(IValidator):
    """Turns a hypothesis into a Fact when it clears the confidence floor.

    ADR-011 §3 (v0.1): accept when the triple has 3 non-empty fields AND the
    Evaluation confidence >= `min_confidence` (default 0.5). The platform then
    applies its own, stricter write threshold (default 0.7).
    """

    def __init__(
        self,
        checker: Optional[IFactChecker] = None,
        min_confidence: float = 0.5,
        actor: str = "HeuristicValidator",
    ) -> None:
        self._checker = checker or HeuristicFactChecker()
        self.min_confidence = min_confidence
        self.actor = actor

    def validate(self, hypothesis: Hypothesis, scorecard: Optional[Scorecard]) -> Optional[Fact]:
        if not hypothesis.is_well_formed():
            return None
        confidence = self._checker.check(hypothesis, scorecard)
        if confidence < self.min_confidence:
            return None

        evidence = hypothesis.evidence
        if scorecard is not None and scorecard.evidence:
            evidence = f"{evidence} | eval: {scorecard.evidence}" if evidence else scorecard.evidence

        fact = Fact(
            subject=hypothesis.subject,
            predicate=hypothesis.predicate,
            object=hypothesis.object,
            source=hypothesis.source,
            evidence=evidence,
            confidence=confidence,
        )
        # LAW 3 / LAW 4: provenance is append-only and starts at validation
        return fact.with_history(action="validated", actor=self.actor)


# --------------------------------------------------------------------------
# Chunking (v0.1: stdlib-only paragraph split — LAW: stdlib-first)
# --------------------------------------------------------------------------
def chunk_document(text: str) -> List[str]:
    """Split a document into paragraph chunks on blank lines.

    v0.1 deliberately avoids langchain/tiktoken. v1.0 -> sentence-aware split.
    """
    if not text:
        return []
    return [c.strip() for c in text.split("\n\n") if c.strip()]


# --------------------------------------------------------------------------
# KnowledgePlatform — the orchestrator
# --------------------------------------------------------------------------
class KnowledgePlatform:
    """Document in, verified Facts out.

    Args:
        extractor: IEntityExtractor port (LLM-backed adapter in production).
        validator: IValidator port (heuristic in v0.1).
        graph:     IKnowledgeGraph port (accepts Facts only).
        scorer:    optional callable producing Evaluation evidence per hypothesis.
        min_confidence: write threshold; below it a hypothesis is rejected
                        (ADR-011 §3: > 0.7 by default).
    """

    def __init__(
        self,
        extractor: IEntityExtractor,
        validator: IValidator,
        graph: IKnowledgeGraph,
        scorer: Optional[ScorerFn] = None,
        min_confidence: float = 0.7,
    ) -> None:
        self._extractor = extractor
        self._validator = validator
        self._graph = graph
        self._scorer = scorer
        self.min_confidence = min_confidence

    def ingest(
        self,
        text: str,
        document_id: str = "doc",
        context: Optional[PolicyContext] = None,
    ) -> IngestReport:
        if context is None:
            context = PolicyContext(query=ModelQuery(task="entity_extraction", prompt=""))

        report = IngestReport(document_id=document_id)
        chunks = chunk_document(text)
        report.chunks = len(chunks)

        for idx, chunk in enumerate(chunks):
            hypotheses = self._extractor.extract_relations(chunk, context)
            report.hypotheses += len(hypotheses)
            report.audit_log.append(
                f"chunk {idx}: {len(hypotheses)} hypotheses from "
                f"{len(chunk)} chars"
            )

            for h in hypotheses:
                # provenance: remember which document the claim came from
                if document_id and document_id not in h.source:
                    h = Hypothesis(
                        subject=h.subject,
                        predicate=h.predicate,
                        object=h.object,
                        source=f"{h.source}@{document_id}" if h.source else document_id,
                        evidence=h.evidence or chunk,
                        confidence=h.confidence,
                    )

                scorecard = self._scorer(h) if self._scorer else None
                fact = self._validator.validate(h, scorecard)

                if fact is None:
                    report.rejected.append(h)
                    report.audit_log.append(
                        f"rejected (validator): {h.subject}-{h.predicate}->{h.object}"
                    )
                    continue

                if fact.confidence <= self.min_confidence:
                    # stays a hypothesis: measured, recorded, NOT knowledge (LAW 5)
                    report.rejected.append(h)
                    report.audit_log.append(
                        f"rejected (confidence {fact.confidence:.2f} <= "
                        f"{self.min_confidence:.2f}): "
                        f"{fact.subject}-{fact.predicate}->{fact.object}"
                    )
                    continue

                stored = fact.with_history(action="stored", actor="KnowledgePlatform")
                if self._graph.add_fact(stored):
                    report.accepted.append(stored)
                    report.audit_log.append(
                        f"accepted (confidence {stored.confidence:.2f}): "
                        f"{stored.subject}-{stored.predicate}->{stored.object}"
                    )
                else:
                    report.audit_log.append(
                        f"duplicate: {stored.subject}-{stored.predicate}->{stored.object}"
                    )

        report.audit_log.append(
            f"summary: {len(report.accepted)}/{report.hypotheses} accepted "
            f"(rate {report.acceptance_rate:.2f})"
        )
        return report

    # --- read side ---------------------------------------------------------
    def facts(self) -> List[Fact]:
        return self._graph.facts()

    def find(self, subject=None, predicate=None, object=None) -> List[Fact]:
        return self._graph.find(subject=subject, predicate=predicate, object=object)
