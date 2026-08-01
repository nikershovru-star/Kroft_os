---
tags: [kroft, adr, eventbus, architecture]
created: 2026-07-31
status: draft
---

# ADR-003 — Event Bus

**Status:** Draft (Wave 0)
**Supersedes:** Hermes Kernel v2 ADR-002

## Context
Platforms interact through events, not direct calls (*Event Driven*).

## Decision
- Kernel owns a typed Event Bus; events are first-class `kernel.events` types.
- Async by design; subscribers are platform adapters.
- Trace/Request IDs propagate on every event (ADR-002 Observability).

## Consequence
- Loose coupling between platforms; new platforms subscribe without kernel edits.
