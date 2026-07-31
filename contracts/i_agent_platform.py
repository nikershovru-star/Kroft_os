"""(contracts) IAgentPlatform — Agent Platform port (Wave 11, ADR-014).

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

Wave 11 closes the gap between the pre-existing agent core (Stage 33/34:
`IAgent` + `ToolRegistry` + `АgentService`) and the Wave 5-10 platforms. This
port is the *orchestration* boundary: the platform coordinates Planner +
Memory + Knowledge + Tools + Workflow + Policies + LLM + Evaluator and returns
a single, traceable `AgentResult`.

Definition of Done (Roadmap Wave 11):

    Agent = Planner + Memory + Knowledge + Tools + Workflow + Policies + LLM + Evaluator

`AgentResult` is frozen (like `Workflow`/`Step` in Wave 10) so a run is
reproducible and the result is data, not a side effect. There are NO time
fields — timing belongs in an Evaluation `Scorecard`, not in the agent record.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional, Tuple

from contracts.i_policy import PolicyContext
from contracts.i_workflow import Workflow


class AgentStatus:
    """Lifecycle of an agent run (immutable taxonomy)."""

    DONE = "done"
    FAILED = "failed"
    PARTIAL = "partial"

    ALL = (DONE, FAILED, PARTIAL)


@dataclass(frozen=True)
class AgentResult:
    """Traceable outcome of one agent run (ADR-014 §2.1).

    Carries the evidence trail required by LAW 4: what was planned, how it was
    executed, what was remembered, what knowledge was consulted, how it was
    measured, which routes were chosen, and what the tools returned.
    """

    goal: str
    workflow: Workflow
    status: str = AgentStatus.DONE
    memory_refs: Tuple[str, ...] = ()
    knowledge_hits: Tuple[str, ...] = ()
    eval_summary: Tuple[str, ...] = ()
    route_log: Tuple[str, ...] = ()
    tool_results: Tuple[str, ...] = ()
    error: str = ""

    def with_memory(self, *refs: str) -> "AgentResult":
        return self.__class__(**{**self.__dict__, "memory_refs": self.memory_refs + tuple(refs)})

    def with_knowledge(self, *hits: str) -> "AgentResult":
        return self.__class__(**{**self.__dict__, "knowledge_hits": self.knowledge_hits + tuple(hits)})

    def with_eval(self, *lines: str) -> "AgentResult":
        return self.__class__(**{**self.__dict__, "eval_summary": self.eval_summary + tuple(lines)})

    def with_routes(self, *routes: str) -> "AgentResult":
        return self.__class__(**{**self.__dict__, "route_log": self.route_log + tuple(routes)})

    def with_tools(self, *results: str) -> "AgentResult":
        return self.__class__(**{**self.__dict__, "tool_results": self.tool_results + tuple(results)})

    def with_status(self, status: str, error: str = "") -> "AgentResult":
        return self.__class__(**{**self.__dict__, "status": status, "error": error})

    @property
    def is_success(self) -> bool:
        return self.status in (AgentStatus.DONE, AgentStatus.PARTIAL)


class IAgentPlatform(abc.ABC):
    """Coordinate all subsystems to fulfil a goal (ADR-014 §2.3)."""

    @abc.abstractmethod
    def run(self, goal: str, context: Optional[PolicyContext] = None) -> AgentResult:
        """Plan and execute `goal`, returning a traceable, frozen result."""
        raise NotImplementedError
