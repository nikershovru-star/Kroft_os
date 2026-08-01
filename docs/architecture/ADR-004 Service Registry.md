---
tags: [kroft, adr, registry, architecture]
created: 2026-07-31
status: draft
---

# ADR-004 — Service Registry

**Status:** Draft (Wave 0)

## Context
Kernel must discover and manage services uniformly (*Everything is a Resource*).

## Decision
- Service Registry: auto-register on import/boot; unified lifecycle
  (init/start/stop/health) for every service.
- Capability tags let platforms find providers declaratively.

## Consequence
- Kernel knows only the Registry, not concrete services (Wave 4 principle).
- Enables Plugin Platform later without kernel changes.
