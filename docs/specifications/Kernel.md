---
tags: [kroft, spec, kernel]
created: 2026-07-31
status: draft
---

# Specification — Kernel

Microkernel owning: Service Registry, Event Bus, DI, Config, Lifecycle, Health.
Depends only on `kernel.domain` + `kernel.events` (axis-gate, tach).

## Boot sequence
1. Load config (from `kroft_os.yaml`).
2. Instantiate Event Bus.
3. Discover & auto-register services (Registry).
4. Wire DI.
5. Start lifecycle (init → start), run health checks.

## Hard rules
- No external library in kernel core.
- No `git stash`/`stash pop`; no merge/push of foreign branches.
- Axis-gate enforced: domain layer never imports providers.
