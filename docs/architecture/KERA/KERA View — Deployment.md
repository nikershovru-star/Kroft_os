---
tags: [kroft, kera, view, deployment, physical]
created: 2026-08-01
author: Hermes
status: v1.0
view_of: KERA
summary: "Deployment View — топология развёртывания (адаптация Physical View)."
---

# KERA View — Deployment

> Deployment (Physical) View (Kruchten): топология компонентов на узлах. Для KROFT —
> текущая реальность: single-node Python; future — multi-node через ICoordinator (ADR-021 A8).

## Текущее (Phase 1–6)
- **Single process**: `python -m runtime` → Kernel READY. Все компоненты — в одном процессе.
- **Composition Root** (bootstrap_v2): единственная точка wiring (KL-010).
- **AKB**: вне процесса, в `docs/architecture/akb/` (читается tests/, не runtime).

## Будущее (Phase 8, optional)
- **Multi-node**: ICoordinator распределяет акторы (Orleans, ADR-021 A6).
- **Agents**: Research Mesh agents могут быть отдельными процессами (services/), связь через EventBus.
- **External LLM** (OmniRoute): ВНЕ domain, только base_url (memory).

## Связь с KERA
- KERA §2 (Core/Services/Meta слои). Здесь — физическое размещение слоёв.
- LAW K8: Meta-layer (LLM/agents) НЕ в runtime-процессе как импорт; общение через порты/EventBus.

## Честная оценка
Deployment View сейчас тривиален (single-node) — это НОРМАЛЬНО («not all architectures
need full 4+1»). Он важен при Phase 8. Преждевременная multi-node-детализация = over-engineering.
