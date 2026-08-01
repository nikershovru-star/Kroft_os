---
tags: [kroft, kera, view, logical]
created: 2026-08-01
author: Hermes
status: v1.0
view_of: KERA
summary: "Logical View — компоненты и контракты KROFT (что система делает для пользователя/агента)."
---

# KERA View — Logical

> Logical View (по Kruchten): функциональность системы, объектная структура. Для KROFT —
> это компоненты и контракты (contracts/*), без runtime-деталей.

## Компоненты (логические)
- **Kernel** (`kernel/`): IKernel, lifecycle. Импортирует только contracts (LAW K1).
- **Runtime** (`runtime/`): ComponentRegistry, Supervisor, EventBus, Recovery, HotReload.
- **Contracts** (`contracts/`): порты (IAgentPlatform, IComponentController, IProcess, IEventBus...).
- **Services/Platforms**: Agent/Memory/Knowledge/Policy/Eval/Workflow/Optimization/Autonomy (волны 11–14).
- **Meta-layer**: Research Mesh agents, AKB (docs/).

## Контракты (grains)
- Каждый crossing-boundary вызов — через `contracts/` Protocol (Interface Standard I1).
- ComponentRegistry активирует компоненты по manifest (Plugin Pattern, PL2).
- Kernel НЕ знает про сервисы (LAW K3) — только через порты.

## Связь с KERA
- KERA §2 (3 слоя), §4 (10 платформ P1–P10). Здесь — логическая детализация слоёв.
- НЕ включает deployment-топологию (см. Deployment View) и runtime-потоки (Runtime View).

## Честная оценка
Logical View стабилен (меняется при добавлении платформы/порта). Detailing ограничен
contracts + kernel/runtime — НЕ дублирует код. LAW K1/K2/K3 здесь первичны.
