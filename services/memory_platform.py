"""MemoryPlatform — Wave 9 orchestrator (ADR-012 Phase D).

Roles (ADR-012 §2.1): Working / Session / Long-Term / Semantic / Procedural.
They are expressed as TAGS over one storage port, not five interfaces.

Dependency rule (LAW 2): this module imports ONLY `contracts`. Stores arrive as
`IMemoryStore` ports; semantic retrieval as `ISemanticMemory`. It never imports
`adapters.in_memory_memory_store`, so swapping the engine (SQLite v0.5,
vector-store v1.0) does not touch this file — that IS the Wave 9 Definition of
Done ("memory works independently of the concrete engine").

Service modules must not import sibling services either (arch gate), which is
why `InMemoryProceduralMemory` lives here rather than in another service.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from contracts.i_llm import ModelQuery
from contracts.i_memory import (
    ConsolidationReport,
    IMemoryStore,
    IProceduralMemory,
    ISemanticMemory,
    MemoryItem,
    MemoryKind,
    MemoryQuery,
    Procedure,
)
from contracts.i_policy import CallRecord

DEFAULT_CONTEXT_HEADER = "Контекст предыдущего диалога:"


# --------------------------------------------------------------------------
# Procedural memory (v0.1) — 'how to do it', consumed by Wave 10
# --------------------------------------------------------------------------
class InMemoryProceduralMemory(IProceduralMemory):
    """Remembers execution patterns and their success rate.

    Deliberately tiny in v0.1: Wave 10 (Workflow) is the real consumer, so the
    contract exists now and the behaviour stays honest — we record outcomes and
    recall the best-known variant, we do not pretend to plan.
    """

    def __init__(self) -> None:
        self._procedures: Dict[str, Dict[str, Any]] = {}
        self._skills: Dict[str, "Procedure"] = {}

    def record_procedure(self, name: str, steps: List[str], success: bool) -> None:
        entry = self._procedures.setdefault(
            name, {"name": name, "steps": list(steps), "runs": 0, "successes": 0}
        )
        entry["runs"] += 1
        if success:
            entry["successes"] += 1
            # keep the steps of the most recent SUCCESSFUL run
            entry["steps"] = list(steps)
        entry["success_rate"] = entry["successes"] / float(entry["runs"])

    def recall_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        entry = self._procedures.get(name)
        return dict(entry) if entry else None

    # --- ТЗ-SKILL-01: capability-keyed consolidated Procedure (skill) ---
    def store_skill(self, skill: "Procedure") -> None:
        self._skills[skill.capability] = skill

    def recall_skill_by_capability(self, capability: str) -> Optional["Procedure"]:
        return self._skills.get(capability)

    def list_skills(self) -> List["Procedure"]:
        return list(self._skills.values())

    def has_skill(self, capability: str) -> bool:
        return capability in self._skills


# --------------------------------------------------------------------------
# MemoryPlatform
# --------------------------------------------------------------------------
class MemoryPlatform:
    """Session/Working/Long-Term orchestration over IMemoryStore ports.

    Args:
        session_store: store for Working + Session items.
        long_term_store: store for consolidated knowledge. May be the SAME
            object as `session_store` in v0.1 — roles are tags, not engines.
        semantic: optional ISemanticMemory for meaning-based retrieval.
        procedural: optional IProceduralMemory (defaults to the in-process one).
        importance_floor: consolidation threshold (ADR-012: > 0.5).
    """

    def __init__(
        self,
        session_store: IMemoryStore,
        long_term_store: Optional[IMemoryStore] = None,
        semantic: Optional[ISemanticMemory] = None,
        procedural: Optional[IProceduralMemory] = None,
        importance_floor: float = 0.5,
    ) -> None:
        self._session = session_store
        self._long_term = long_term_store if long_term_store is not None else session_store
        self._semantic = semantic
        self._procedural = procedural or InMemoryProceduralMemory()
        self.importance_floor = importance_floor
        self._seq = 0

    # --- write side --------------------------------------------------------
    def remember_turn(
        self,
        session_id: str,
        content: str,
        role: str = "user",
        importance: float = 1.0,
        ttl: Optional[int] = None,
        source: str = "",
    ) -> MemoryItem:
        """Append one dialogue turn to Session memory."""
        self._seq += 1
        item = MemoryItem(
            key=f"session:{session_id}:{self._seq:06d}",
            content=content,
            timestamp=time.time(),
            ttl=ttl,
            importance=importance,
            tags=(MemoryKind.SESSION, f"session:{session_id}", f"role:{role}"),
            source=source,
        )
        self._session.put(item)
        return item

    def remember_working(
        self,
        key: str,
        content: str,
        ttl: Optional[int] = 300,
        importance: float = 0.4,
    ) -> MemoryItem:
        """Scratch space for the current task (short TTL by default)."""
        item = MemoryItem(
            key=f"working:{key}",
            content=content,
            timestamp=time.time(),
            ttl=ttl,
            importance=importance,
            tags=(MemoryKind.WORKING,),
        )
        self._session.put(item)
        return item

    # --- read side ---------------------------------------------------------
    def session_turns(self, session_id: str, limit: int = 10) -> List[MemoryItem]:
        """Most recent turns first."""
        return self._session.query(
            MemoryQuery(tags=[MemoryKind.SESSION, f"session:{session_id}"], limit=limit)
        )

    def recall(self, text: str, limit: int = 5) -> List[MemoryItem]:
        """Meaning-based retrieval; empty when no semantic port is wired."""
        if self._semantic is None:
            return []
        return self._semantic.search(text, limit=limit)

    # --- Router integration (ADR-012 §2.4) ---------------------------------
    def build_context(self, session_id: str, limit: int = 5) -> str:
        """Render the last `limit` turns oldest-first as prompt context."""
        turns = self.session_turns(session_id, limit=limit)
        if not turns:
            return ""
        # oldest-first for reading order; key breaks same-tick ties (see store)
        ordered = sorted(turns, key=lambda i: (i.timestamp, i.key))
        lines = []
        for item in ordered:
            role = next(
                (t.split(":", 1)[1] for t in item.tags if t.startswith("role:")), "user"
            )
            lines.append(f"{role}: {item.content}")
        return "\n".join(lines)

    def augment_query(
        self,
        query: ModelQuery,
        session_id: str,
        limit: int = 5,
        header: str = DEFAULT_CONTEXT_HEADER,
    ) -> ModelQuery:
        """Return a NEW ModelQuery whose prompt carries session context.

        The input query is never mutated (LAW 3) — callers keep their object.
        With no history the query is returned unchanged, so wiring memory in
        can never make a cold-start call worse.
        """
        context = self.build_context(session_id, limit=limit)
        if not context:
            return query

        prompt = f"{header}\n{context}\n\n{query.prompt}"
        return ModelQuery(
            task=query.task,
            reasoning=query.reasoning,
            local=query.local,
            json_mode=query.json_mode,
            cheap=query.cheap,
            context_window=query.context_window,
            preferred_provider=query.preferred_provider,
            prompt=prompt,
        )

    # --- Policy integration (ADR-009 PolicyContext.history) ----------------
    def call_history(self, session_id: str, limit: int = 10) -> List[CallRecord]:
        """Project remembered LLM calls into CallRecords for PolicyContext."""
        items = self._session.query(
            MemoryQuery(tags=[f"session:{session_id}", "llm_call"], limit=limit)
        )
        return [
            CallRecord(model=i.source or "unknown", timestamp=i.timestamp)
            for i in items
        ]

    # --- consolidation (Session -> Long-Term) ------------------------------
    def consolidate(self, session_id: str) -> ConsolidationReport:
        """Promote important session items into Long-Term memory.

        LAW 4: every promotion/skip is explained in the report.
        LAW 5: counts are reported, not assumed.
        """
        report = ConsolidationReport(session_key=session_id)
        items = self._session.query(
            MemoryQuery(tags=[MemoryKind.SESSION, f"session:{session_id}"])
        )
        report.examined = len(items)

        for item in items:
            if item.importance <= self.importance_floor:
                report.skipped.append(item)
                report.audit_log.append(
                    f"skipped (importance {item.importance:.2f} <= "
                    f"{self.importance_floor:.2f}): {item.key}"
                )
                continue

            promoted = item.with_tags(MemoryKind.LONG_TERM, MemoryKind.CONSOLIDATED)
            # long-term memory does not inherit the session TTL
            promoted = MemoryItem(
                key=f"longterm:{item.key}",
                content=promoted.content,
                timestamp=promoted.timestamp,
                ttl=None,
                importance=promoted.importance,
                tags=promoted.tags,
                embedding=promoted.embedding,
                source=promoted.source or f"session:{session_id}",
            )
            self._long_term.put(promoted)
            report.promoted.append(promoted)
            report.audit_log.append(
                f"promoted (importance {item.importance:.2f}): {item.key} -> {promoted.key}"
            )

        report.audit_log.append(
            f"summary: {len(report.promoted)}/{report.examined} promoted "
            f"(rate {report.promotion_rate:.2f})"
        )
        return report

    # --- maintenance -------------------------------------------------------
    def cleanup(self, compress_threshold: Optional[float] = None) -> Dict[str, int]:
        """Run TTL eviction and (optionally) compression. Returns counts (LAW 5)."""
        stats = {"expired": self._session.delete_expired(), "compressed": 0}
        if self._long_term is not self._session:
            stats["expired"] += self._long_term.delete_expired()
        if compress_threshold is not None:
            stats["compressed"] = self._session.compress(compress_threshold)
        return stats

    # --- procedural --------------------------------------------------------
    def record_procedure(self, name: str, steps: List[str], success: bool) -> None:
        self._procedural.record_procedure(name, steps, success)

    def recall_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        return self._procedural.recall_procedure(name)
