---
tags: [kroft, kera, view, runtime, process]
created: 2026-08-01
author: Hermes
status: v1.0
view_of: KERA
summary: "Runtime View — процессы, события, восстановление во время выполнения (адаптация Process View)."
---

# KERA View — Runtime

> Runtime (Process) View (Kruchten): concurrency, synchronization, runtime behaviour.
> Для KROFT — это как компоненты живут, общаются через EventBus, восстанавливаются.

## Runtime элементы
- **ProcessState FSM** (Phase 4): INSTANTIATING→RUNNING→DEGRADED→QUARANTINED→RECOVERING.
- **Supervisor** (ADR-021): supervision tree, MaxR/MaxT, escalation.
- **EventBus** (ADR-003): pub/sub сигналов (KL-016 Signal) между компонентами.
- **Recovery** (ADR-020 Phase 4): policy-driven backoff, Reconciler (durable state), no single sync sleep (F1 forbidden).
- **Hot Reload** (ADR-020 Phase 5): ConfigService publishes `config.changed`, ComponentController.swap без Kernel.stop.

## Поток (пример)
```
component crash → Supervisor detects → RecoveryPolicy (backoff) →
Reconciler restores → component RUNNING (Kernel НЕ остановлен)
```
## Связь с KERA
- KERA §2 (Core), §4 (Runtime Platform P4). Здесь — динамика.
- LAW K8: runtime/* только contracts+stdlib (Recovery/Supervisor НЕ импортируют services).

## Честная оценка
Runtime View критичен для надёжности. Chaos-доказательство (KES#7) проверяет его.
Известный gap: Phase 4 recover — single sync (без yield между попытками); задокументирован
как known-limitation (см. org_memory.yaml ADR-020). Не скрыто.
