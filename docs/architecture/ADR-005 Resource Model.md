---
tags: [kroft, adr, resource, architecture]
created: 2026-07-31
status: draft
---

# ADR-005 — Resource Model

**Status:** Draft (Wave 0)

## Context
Models, memory, graph, tools, workflows are all **resources** of the kernel
(*Everything is a Resource*).

## Decision
- Uniform `Resource` descriptor: id, type, capabilities, owner, lifecycle, metrics hook.
- Resource Manager (see `docs/specifications/ResourceManager.md`) mediates access.
- Policy gates every resource request (ADR-007).

## Consequence
- Platforms expose resources uniformly; apps compose them without knowing internals.
- Enables the platform tree: Model/Memory/Knowledge → Workflow/Tool → Security/Observability → Apps.
