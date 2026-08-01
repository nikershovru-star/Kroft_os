---
tags: [kroft, kera, view, security]
created: 2026-08-01
author: Hermes
status: v1.0
view_of: KERA
summary: "Security View — границы, доверие, human-approve, изоляция слоёв."
---

# KERA View — Security

> Cross-cutting View: как KROFT обеспечивает доверие и границы. Связан с KP-006 (Humans
> Approve) и LAW K5/K7.

## Границы доверия (Boundaries, KL-013)
- **Core ↔ Services**: Kernel импортирует только contracts (LAW K1). Services НЕ модифицируют
  Kernel (LAW K3). Нарушение = arch-gate F1/F4 fail.
- **Services ↔ Meta**: Research Mesh agents — компоненты в services/, НЕ runtime/ (LAW K8).
  External LLM (OmniRoute) — ВНЕ domain, только base_url.
- **Human ↔ System**: apply/approve требует человека (KP-006, LAW K5/K7). Self-improvement
  (L16) — human-in-loop (Gödel-boundary, ADR-024).

## Изоляция
- Supervisor isolates сбой (Fault Isolation, KES#7): падение компонента НЕ каскадирует.
- QUARANTINED state защищает систему от деградирующего компонента.
- EventBus — единственный канал меж-компонентной связи (нет прямых вызовов через границы).

## Связь с KERA
- KERA §2 (Boundaries), §6 (LAW K1–K8 как lenses). Здесь — security-аспект границ.
- Governance (L12): PR-check блокирует K-нарушения до merge (arch-gate читает laws.yaml).

## Честная оценка
Security View сейчас = boundary-discipline (не auth/crypto — это платформы волн). Для
инженерной ОС критична именно целостность границ (LAW K8), а не периметр. Auth добавится
в Security Platform (P7) когда дойдёт очередь — НЕ преждевременно.
