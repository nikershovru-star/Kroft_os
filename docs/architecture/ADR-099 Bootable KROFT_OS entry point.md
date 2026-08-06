---
id: ADR-099
title: Bootable KROFT_OS — single entry point lifting the whole stack (ТЗ-RUN-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-088   # LIVE-01 living core
  - ADR-092   # EVOLUTION-01 SkillEvolver
  - ADR-093   # MARKETPLACE-01 SkillRepository
  - ADR-094   # FED-REPL-01 SkillDistributor
  - ADR-097   # DESKTOP-01 dashboard
  - ADR-089   # OMNI-01 LLM routing
decision: >-
  ТЗ-RUN-01 — кульминация серии capability+security ТЗ: одна команда поднимает весь стек
  (kernel + опц. LLM + эволюция + опц. федерация + dashboard) с live-демо циклом. K5-разведка:
  build_kernel(kernel/cognitive_kernel.py), SkillEvolver, InMemoryLayeredMemory/InMemoryProceduralMemory,
  build_default_dashboard (DESKTOP-01), build_llm_client/OmniRouter (OMNI-01), SkillDistributor/
  SkillRepository/ReferenceTrustRegistry (FED-REPL-01) — УЖЕ есть. run_kroft.py — ЧИСТАЯ КОМПОЗИЦИЯ
  (НЕ дублирует run_evolution.py: тот владеет persistence/autosave/live-loop; run_kroft — верхнеуровневый
  "boot EVERYTHING + dashboard + demo evolution" aggregator). KroftConfig (dataclass) + KroftApp.boot +
  run_demo loop + CLI (--node-id/--llm/--federation/--ticks/--no-demo). Graceful degradation: LLM и
  федерация ОПЦИОНАЛЬНЫ; без них — детерминированный LLM-free run (I-09). Эволюция через SkillEvolver
  (heuristic, deterministic). Dashboard read-only (DESKTOP-01). Флаг C: standalone entry. Флаг 1b: тесты
  отдельно.
evidence_level: V
addresses:
  - TZ-RUN-01
---
## Context
All layers (LIVE/OMNI/AGENT-LOOP/KNOWLEDGE-ENGINE/EVOLUTION/MARKETPLACE/FED-REPL/DESKTOP + AUTHOR-KEYS/
KEYDIST security) are ready, but there is NO single entry point lifting the WHOLE stack together with a
live demo. ТЗ-RUN-01 gives run_kroft.py: boot kernel + optional LLM + federation + evolution loop +
dashboard render, in one runnable entry with a live-demo loop. Culmination of the series; answers
"run it and watch evolution".

## Decision
- composition/run_kroft.py (Флаг C): KroftConfig (dataclass) + KroftApp. Boot reuses build_kernel
  (kernel/cognitive_kernel.py — CognitiveKernel with FSM tick), InMemoryLayeredMemory + InMemoryProceduralMemory,
  SkillEvolver (sandbox + memory injected), build_default_dashboard (DESKTOP-01), optional build_llm_client/
  OmniRouter (OMNI-01), optional SkillDistributor + SkillRepository + ReferenceTrustRegistry (FED-REPL-01 via
  LoopbackTransport). run_demo(ticks) loops: kernel.tick(Intent) + evolve demo skill + render dashboard snapshot.
  CLI: `python composition/run_kroft.py [--node-id X] [--llm none|auto|mock] [--federation] [--ticks N] [--no-demo]`.
- K5: NO new contract/port. Reuses existing factories/components (does NOT duplicate run_evolution.py).
- Graceful degradation: llm="none" (LLM-free deterministic) | "auto" (real endpoint, never called in demo) |
  "mock" (deterministic _MockLlm). federation optional (disabled by default).
- I-09: deterministic LLM-free evolution (SkillEvolver heuristic). O1/DESKTOP-01: dashboard read-only.

## Consequences
- Single command lifts the whole stack; evolution visible over time (demo skill v1 -> v2); dashboard renders
  kernel state (node/FSM/memory/agents/trust/models/tasks).
- No network/external model required for the default LLM-free demo (graceful degradation).
- Non-scope (post-MVP): real multi-host TCP, full pyautogui GUI, Ed25519/PKI (KEYDIST-01 Флаг 3), real
  bootstrap/OCSP revocation (KEYDIST-01 Флаг 1/2).
- Series capability+security ТЗ COMPLETE: 7 capability stages + 2 capstones + security core closed.
