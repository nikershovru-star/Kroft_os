---
id: ADR-097
title: Observability dashboard — read-only kernel-state snapshot + deterministic renderer (ТЗ-DESKTOP-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-067   # OBS-01 LiveMetricsCollector / RuntimeSupervisor (operational metrics)
  - ADR-062   # RT-01 Runtime Reflection
  - ADR-054   # Cognitive Kernel Constitution (FSM states)
  - ADR-072   # IDT-01 TrustRegistry / IdentityRegistry
decision: >-
  Финальный capability-этап (Этап 8): пользователь должен ВИДЕТЬ состояние ядра (память, агентов,
  доверие, модели, задачи, FSM-состояние). Полноценный GUI (pyautogui) платформозависим — post-MVP.
  Трактобельное ядро этапа — read-only observability-дашборд: детерминированный snapshot состояния
  ядра + рендерер (text/JSON). K5-разведка: существующая OBS-01 инфра (ILiveMetricsCollector /
  RuntimeSupervisor) отвечает на «как хорошо система работает?» (operational RATIO metrics) — НЕ
  дублируем; dashboard отвечает на «какое ТЕКУЩЕЕ СТРУКТУРНОЕ состояние ядра?» (memory/agents/trust/
  models/tasks/FSM). Это отдельный boundary (one-port-per-boundary). DashboardSnapshotter — ЧИСТЫЙ
  aggregator/renderer: принимает READ-ONLY providers (callables) и собирает frozen DashboardSnapshot.
  Composition (build_default_dashboard) связывает providers с РЕАЛЬНЫМИ компонентами через их
  существующие ПУБЛИЧНЫЕ аксессоры (K5: reuse, НЕ дублирует state-аксессоры). Dashboard НЕ импортирует
  kernel/identity/services — только callables, поэтому СТРУКТУРНО не может мутировать ядро (O1-style safe
  observation). captured_at — инъектируемая последовательность (Lamport), НЕ wall-clock (K5 determinism).
evidence_level: V
addresses:
  - TZ-DESKTOP-01
---

## Context
Все 7 capability-этапов замкнуты; остался пользовательский слой (Этап 8). OBS-01 уже даёт
operational metrics (LiveMetricsCollector + RuntimeSupervisor), но пользователю нужен СТРУКТУРНЫЙ
снимок: что сейчас в памяти, кто агенты, какое доверие, какие модели, какие задачи, в каком FSM-состоянии
ядро. Полноценный pyautogui-GUI платформозависим (post-MVP). Read-only snapshot + text/JSON рендерер —
первый пользовательский surface, детерминированный и НЕ мутирующий ядро.

## Decision
- **contracts/i_dashboard.py**: `DashboardSnapshot` (frozen VO: node_id, kernel_state, memory_counts,
  agents, trust, models, tasks, captured_at) + `IDashboard` (snapshot/render_text/render_json). NEW seam;
  НЕ дублирует OBS-01 (ILiveMetricsCollector — separate boundary).
- **services/desktop_dashboard.py** (K6: services->contracts only): `DashboardSnapshotter` — PURE
  aggregator/renderer. Принимает `providers` (dict name->callable), `snapshot()` вызывает их (read-only)
  и собирает frozen VO. `render_text`/`render_json` детерминированы (json sort_keys). НЕ импортирует
  kernel/identity/services — только callables => структурно read-only (не может мутировать ядро).
- **composition/desktop_dashboard_factory.py** (Флаг C): `build_default_dashboard(kernel, memory_platform,
  trust_registry, identity_registry, task_store, model_registry, ...)` — строит providers из РЕАЛЬНЫХ
  компонентов через их публичные аксессоры (K5: reuse). `_mem_counts` duck-typed (layered `get_episodes/
  get_semantic/get_normative` ИЛИ procedural `list_skills`). `_trust_authors` duck-typed (публичный
  `authors()` ИЛИ `_by_author`). НЕ в build_kernel.
- **READ-ONLY**: snapshotter пишет значения в frozen VO и НИЧЕГО не пишет обратно в ядро/HARD/FSM
  (O1-safe observation). missing component => empty tuple (graceful).

## Consequences
- Пользователь видит детерминированный снимок ядра (text/JSON). Поверхности: memory (counts), agents,
  trust (author->score), models, tasks, kernel_state (FSM name), node_id.
- НЕ дублирует OBS-01; dashboard (structural state) + OBS-01 (operational metrics) — ортогональные boundary.
- Non-scope (post-MVP): полноценный pyautogui/оконный GUI; Ed25519/PKI/key-distribution (см. AUTHOR-KEYS-01);
  live-refresh loop (опц. provider может переопределяться для refresh, но сам dashboard stateless).
- I-09: frozen VO + json sort_keys => детерминизм; O1: read-only (не мутирует ядро); Флаг C: НЕ в build_kernel.
- Замыкает ВСЕ 7 capability-этапов + 2 капстоуна: визия функционально завершена (остался post-MVP GUI + security).
