---
id: ADR-048
title: "Agent Society — roles, reputation, negotiation, voting, auctions (TZ-019)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.79
confidence: high
risk: medium
related: [TZ-019, TZ-AGENT-001, ADR-045, WP-14, Wave-3]
---

# ADR-048: Agent Society (TZ-019)

## 1. Context
Вместо одного агента — общество. TZ-AGENT-001 дал IAgentPlatform (single agents).
TZ-019 добавляет: Roles, Skills, Reputation, Negotiation, Voting, Auctions, Conflict
Resolution, Resource Sharing. Топология: Planner → Research → Developer → Reviewer →
Supervisor (ACM survey LLM-MAS 2025 подтверждает эти роли).

## 2. Research Synthesis (2026-08-02)
- **Negotiation/Argumentation** (AAAI WMAC 2026): explicit conflict resolution через
  structured dialogue; большинство Agentic AI lacks it. Escalation: Negotiate → Vote →
  Mediate → Arbitrate (enterprise AI).
- **Roles** (ACM survey LLM-MAS): Orchestrator, Programmer, Reviewer, Tester, Retriever.
- **Market-based pattern** (Confluent): decentralized marketplace — agents negotiate/
  compete за tasks/resources (auctions). AgentNet (arxiv 2504): dynamic specialization.
- **Reputation/Resource Sharing** (survey 2025): reputation → trust; resource-sharing →
  joint decision.

## 3. Decision
Порты в contracts (K1), сервисы в services (K8). Reuse IAgentPlatform (TZ-AGENT-001)
+ IClusterRegistry (TZ-015) для discovery:
- `IRoleRegistry` — agent→role (Planner/Research/Developer/Reviewer/Supervisor).
- `ISkillRegistry` — agent→skills (capabilities).
- `IReputationEngine` — score(agent) += success / -= failure.
- `INegotiation` — propose/counter/accept protocol (argumentation).
- `IVoting` — weighted vote (by reputation) → decision.
- `IAuction` — task/resource allocation via sealed-bid; winner = best bid.
- `IConflictResolution` — escalation ladder (negotiate→vote→mediate→arbitrate).
- `IResourceSharing` — shared resource pool (CPU/GPU/memory/context budget).
- `AgentSocietyService` — orchestrates society (route task by role, resolve conflicts).

## 4. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: conflict resolution НЕ executes agent actions (delegates to IAgentPlatform).
- **K6**: через IAgentPlatform/IClusterRegistry порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
Planner ──▶ Research ──▶ Developer ──▶ Reviewer ──▶ Supervisor
   │(role registry)  (auction alloc)  (voting)  (conflict res)  (reputation)
```

## 6. Validation (когда K5 go)
- role/skill registry; reputation updates; negotiation reaches agreement; voting
  weighted; auction allocates; conflict escalates; resource shared.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-019 (TZ-019); AAAI WMAC 2026 (negotiation), ACM survey LLM-MAS 2025 (roles),
  Confluent market-based, AgentNet arxiv 2504, MAS coordination survey 2025
- TZ-AGENT-001 (IAgentPlatform), TZ-015 (IClusterRegistry)
