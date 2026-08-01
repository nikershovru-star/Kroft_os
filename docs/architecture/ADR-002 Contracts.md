---
tags: [kroft, adr, contracts, architecture]
created: 2026-07-31
status: draft
---

# ADR-002 — Contracts

**Status:** Draft (Wave 1)
**Supersedes:** KnowledgeOS-v5 `contracts/i_*.py` style

## Context
Every platform depends on stable interfaces, never on concrete libraries/APIs
(*Contracts Before Code*, *Provider Agnostic*).

## Decision
- Each contract = `abc.ABC` + `@abstractmethod`, docstring "adapters may import
  contracts + stdlib only".
- Each contract ships: Contract Tests + Golden Tests + docs + version.
- Current ports: `ILlm`, `IEmbedding`, `IModelMetadata`, `IHealth` (ADR-006),
  `IPolicy` (ADR-007, stub). Planned: Memory/Graph/Tool/Storage/Workflow/Policy/Metrics.

## Consequence
- Service never imports openai/ollama/omniroute/mem0 directly.
- Replacing a provider needs zero kernel change.
