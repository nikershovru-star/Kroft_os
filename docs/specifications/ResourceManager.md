---
tags: [kroft, spec, resource]
created: 2026-07-31
status: draft
---

# Specification — ResourceManager

Implements ADR-005 (Resource Model). Mediates access to every kernel resource.

## Resource descriptor
```
Resource:
  id: str
  type: model | memory | graph | tool | workflow | storage
  capabilities: dict
  owner: service_id
  lifecycle: init|start|stop
  metrics_hook: fn
```

## Rules
- Every access goes through Policy check (ADR-007) first.
- Capability discovery: declared + probe + production stats.
- Registry (Wave 4) is the source of truth for resource catalog.
