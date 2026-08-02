---
tags: [kroft, spec, scheduler]
created: 2026-07-31
status: draft
---

# Specification — Scheduler

Part of Workflow Platform (Wave 10). Executes planned tasks with retries,
reflection, and priority.

## Responsibilities
- Queue / cron scheduling of Workflow steps.
- Retry with backoff (Retry Manager).
- Priority ordering (greedy vs queue — open question, see ADR-007).
- Emits lifecycle events to Event Bus (ADR-003).

## Interface (sketch)
```
schedule(workflow, when, priority) -> job_id
cancel(job_id)
status(job_id) -> JobState
```
