"""PHASE 2 — IKroftAgentInterface (universal external-agent contract).

K1 axis-clean: this module imports ONLY contracts + stdlib. It defines the
single universal contract that ANY external AI-agent (Hermes / Codex / Claude /
another KROFT) uses to talk to a KROFT Runtime. KROFT itself stays agnostic to
which agent is calling (ТЗ §2: no ``if hermes:`` branching, no ``HermesKernel``).

The interface is deliberately minimal and agent-agnostic:
    status()  search()  query()  resolve()  audit()  observe()  memory()  knowledge()

Reuse-first: the concrete implementation (services/kroft_agent_interface.py)
delegates to EXISTING services — GraphQueryEngine (search/query/audit/observe/
knowledge) and ReferenceKnowledgeResolution (ADR-028 Э1, resolve). No second
search engine, no duplicated resolution logic.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional


class IKroftAgentInterface(abc.ABC):
    """Universal contract exposed by a KROFT Runtime to external agents.

    Every method returns a plain ``dict`` / ``list`` (machine-readable) so the
    same contract serves CLI, HTTP API, and any agent SDK without special-casing.
    """

    @abc.abstractmethod
    def status(self) -> Dict[str, Any]:
        """Runtime + kernel + knowledge + http health snapshot."""

    @abc.abstractmethod
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Lexical/hybrid node search; returns ranked hits."""

    @abc.abstractmethod
    def query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """Query path over the knowledge graph (hybrid retrieval)."""

    @abc.abstractmethod
    def resolve(self, query: str, level: str = "SYSTEM") -> Dict[str, Any]:
        """Multi-resolution resolution (ADR-028): EVIDENCE..SYSTEM ladder."""

    @abc.abstractmethod
    def audit(self, limit: int = 50) -> Dict[str, Any]:
        """Audit/temporal log of graph mutations."""

    @abc.abstractmethod
    def observe(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """Runtime observability snapshot (health + graph stats)."""

    @abc.abstractmethod
    def memory(self, action: str = "list", **kwargs: Any) -> Dict[str, Any]:
        """Procedural / learning memory access."""

    @abc.abstractmethod
    def knowledge(self, action: str = "stats", **kwargs: Any) -> Dict[str, Any]:
        """Knowledge-graph statistics / introspection."""
