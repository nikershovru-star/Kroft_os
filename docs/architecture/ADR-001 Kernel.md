---
tags: [kroft, adr, kernel, architecture]
created: 2026-07-31
status: draft
---

# ADR-001 — Kernel

**Status:** Draft (Wave 0)
**Supersedes:** Hermes Kernel v2 ADR-001..032 (microkernel line)

## Context
KROFT_OS needs a minimal microkernel that owns lifecycle, DI, event bus,
configuration, and health — independent of any AI technology (LLM, KG, Obsidian,
OmniRoute). Per roadmap principle *Kernel First*.

## Decision
- Kernel = microkernel: Service Registry + Event Bus + DI + Config + Lifecycle + Health.
- Kernel domain depends only on `kernel.domain` + `kernel.events` (axis-gate).
- No external library leaks into the kernel; adapters live outside.

## Consequence
- Platforms (Model, Memory, Knowledge, …) plug in via contracts, not kernel edits.
- Evolution Without Rewrites is enforceable via tach axis-gate.
- Detailed spec: `docs/specifications/Kernel.md`.
