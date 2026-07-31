"""Golden Dataset (Wave 7, ADR-010 §4 / Roadmap Phase C).

IMMUTABLE: any change requires ADR + commit + reason. Built from frozen `Task`
entities (contracts.i_eval.Task) so it cannot be mutated at runtime (LAW 3:
no hidden mutable state). Five categories, each with at least one example.
"""
from __future__ import annotations

from contracts.i_eval import Task, TaskCategory

# Frozen records -> the dataset cannot be edited after module import.
GOLDEN_DATASET: tuple[Task, ...] = (
    # 1) QA
    Task(
        id="qa-001",
        category=TaskCategory.QA,
        input="What is the capital of France?",
        expected="Paris",
        tags={"lang": "en", "domain": "geography"},
    ),
    # 2) Reasoning
    Task(
        id="reasoning-001",
        category=TaskCategory.REASONING,
        input="If all Bloops are Razzies and all Razzies are Lazzies, "
              "are all Bloops definitely Lazzies? Explain.",
        expected="Yes",
        rubric="Correct logical conclusion (transitive implication) with a brief reason.",
        tags={"lang": "en", "type": "syllogism"},
    ),
    # 3) Summarization
    Task(
        id="summary-001",
        category=TaskCategory.SUMMARIZATION,
        input="The quick brown fox jumps over the lazy dog. "
              "A wizard casts a spell of silence. The knight guards the gate at dawn.",
        expected=None,
        rubric="One concise sentence capturing the three distinct events without adding facts.",
        tags={"lang": "en", "len": "short"},
    ),
    # 4) Entity Extraction
    Task(
        id="entity-001",
        category=TaskCategory.ENTITY_EXTRACTION,
        input="Alice met Bob at Acme Corp in London on Monday.",
        expected="Alice; Bob; Acme Corp; London",
        rubric="Extract person, org, and location entities as a semicolon-separated list.",
        tags={"lang": "en", "schema": "PER/ORG/LOC"},
    ),
    # 5) Retrieval
    Task(
        id="retrieval-001",
        category=TaskCategory.RETRIEVAL,
        input="Find the note about the Policy Platform architecture.",
        expected="ADR-009",
        rubric="Return the identifier of the most relevant stored document (ADR-009).",
        tags={"lang": "en", "kind": "doc-id"},
    ),
)


def fetch_dataset() -> tuple[Task, ...]:
    """Return the immutable golden dataset (a copy-tuple of frozen Tasks)."""
    return GOLDEN_DATASET


def fetch_by_category(category: str) -> tuple[Task, ...]:
    return tuple(t for t in GOLDEN_DATASET if t.category == category)
