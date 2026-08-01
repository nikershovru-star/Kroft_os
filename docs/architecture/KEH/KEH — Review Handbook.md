---
tags: [kroft, keh, review-handbook, governance, arch-gate]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KEH
summary: "Review Handbook (KEH) — арх-ревью + Governance (PR-check). Ссылается на KES Decision/Reliability."
---

# KEH — Review Handbook

> Handbook KEH: как ревьюировать архитектуру и код. Выведен из KP-003 (Architecture > Features).
> Связан с Governance (L12) и LAW K1–K8.

## Architecture Review (Уровень 2 зрелости)
- Самокритика: где нарушен SOLID? LAW K1–K8? Что сломается через год? Bottleneck?
- Использует AKB (laws.yaml, patterns/forbidden.yaml) как критерий.

## Governance (PR-check, L12)
- arch-gate читает `laws.yaml` → блокирует K-нарушения до merge.
- Читает `evidence_levels.yaml` → ADR ниже Level III → warn.
- Читает `glossary.yaml` → не-KL термин → warn.

## Chaos Review (KES Reliability Science)
- Значимый компонент требует chaos-proof (failure injection + MTTR) перед «reliable».

## Честная оценка
copilot-instructions.md trick: «give AI reviewer ADRs as instructions». KROFT делает через
arch-gate + AKB. Risk: gate слишком строгий тормозит — митигация: warn vs block разделены
(LAW нарушение = block, evidence/term = warn). LAW K8: arch-gate в tests/, НЕ runtime.
