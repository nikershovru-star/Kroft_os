---
id: RFC-019
title: "Agent Society — roles, reputation, negotiation, voting, auctions (TZ-019)"
status: under_review
date: "2026-08-02"
related: [TZ-019, ADR-048, TZ-AGENT-001, TZ-015]
authors: [kroft-architect]
evidence_level: III
---

# RFC-019: Agent Society (TZ-019)

## 0. Research synthesis (2026-08-02) — см. ADR-048 §2
AAAI WMAC 2026 (negotiation/argumentation, escalation ladder); ACM survey LLM-MAS 2025
(roles); Confluent market-based (auctions); AgentNet arxiv 2504 (dynamic specialization);
MAS coordination survey 2025 (reputation/resource-sharing).

## 1. Problem
TZ-AGENT-001 = single agents (orchestrated). Нет society: ролей, репутации,
переговоров, голосования, аукционов, разрешения конфликтов, sharing ресурсов.

## 2. Proposal — 8 components

### 2.1 `IRoleRegistry` (`contracts/`)
```python
class IRoleRegistry(ABC):
    def assign(self, agent_id: str, role: str) -> None: ...
    def role_of(self, agent_id: str) -> str: ...
    ROLES = ["planner","research","developer","reviewer","supervisor"]
```

### 2.2 `ISkillRegistry` (`contracts/`)
```python
class ISkillRegistry(ABC):
    def add_skill(self, agent_id: str, skill: str) -> None: ...
    def skilled_in(self, skill: str) -> List[str]: ...
```

### 2.3 `IReputationEngine` (`contracts/`)
```python
class IReputationEngine(ABC):
    def reward(self, agent_id: str, delta: float) -> None: ...
    def score(self, agent_id: str) -> float: ...
```

### 2.4 `INegotiation` (`contracts/`)
```python
class INegotiation(ABC):
    def propose(self, a: str, b: str, terms: dict) -> str: ...   # returns proposal_id
    def counter(self, proposal_id: str, terms: dict) -> None: ...
    def accept(self, proposal_id: str) -> bool: ...
```

### 2.5 `IVoting` (`contracts/`)
```python
class IVoting(ABC):
    def vote(self, topic: str, votes: Dict[str, Any], weights: Dict[str,float]) -> Any: ...
```
Weighted by IReputationEngine.score.

### 2.6 `IAuction` (`contracts/`)
```python
class IAuction(ABC):
    def bid(self, task_id: str, agent_id: str, bid: float) -> None: ...
    def close(self, task_id: str) -> str: ...   # winner agent_id (min bid / best skill)
```

### 2.7 `IConflictResolution` (`contracts/`)
```python
class IConflictResolution(ABC):
    def resolve(self, conflict: dict) -> dict: ...
    # escalation: negotiate -> vote -> mediate -> arbitrate(supervisor)
```

### 2.8 `IResourceSharing` (`contracts/`)
```python
class IResourceSharing(ABC):
    def acquire(self, agent_id: str, resource: str, amount: float) -> bool: ...
    def release(self, agent_id: str, resource: str) -> None: ...
```

### 2.9 `AgentSocietyService` (`services/`)
Routes task by IRoleRegistry; allocates via IAuction; resolves conflicts via
IConflictResolution; tracks IReputationEngine. Reuse IAgentPlatform (TZ-AGENT-001) +
IClusterRegistry (TZ-015).

## 3. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: conflict resolution delegates execution to IAgentPlatform (reuse TZ-AGENT).
- **K6**: через IAgentPlatform/IClusterRegistry порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- Negotiation loops — bound rounds (IConflictResolution abort after N).
- Reputation gaming — bounded delta + decay.

## 5. Validation (при K5 go)
- role/skill assign; reputation reward/score; negotiation accept; voting weighted;
  auction winner; conflict escalate; resource acquire/release.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Single orchestrator hardcodes roles — отвергнуто (no society/negotiation).
- Blockchain consensus — отвергнуто (overkill, not local-first).
