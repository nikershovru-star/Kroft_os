---
tags: [kroft, rfc, request-for-comments, proposal, discussion, pre-adr]
created: 2026-08-01
author: Hermes (Architecture Intelligence — по principal-review: RFC между Research и ADR)
status: v1.0 (process layer)
position: "Research → Experiment → RFC → ADR → Implementation"
summary: >-
  RFC (Request for Comments) — уровень ОБСУЖДАЕМОГО предложения, ДО принятия.
  ADR — уже ПРИНЯТОЕ решение. Конвейер: Research → Experiment → RFC (Draft/Review/
  Decided) → ADR → Implementation. RFC позволяет обсуждать до фиксации (human-in-loop,
  KP-006). Индекс RFC — docs/architecture/akb/rfcs.yaml (машинночитаемый).
---

# KROFT RFC Layer v1.0

> RFC — **обсуждаемое** предложение. ADR — **принятое** решение. Без RFC-слоя ADR
> превращается в «ADR-001..147» (никто не понимает архитектуру через год). RFC даёт
> окно для критики ДО фиксации (согласно KP-006 Humans Approve).

---

## Конвейер решений

```
Research (KES#1) ─┐
                   ├─→ Experiment (KES#3) ─→ RFC (Draft→Review→Decided) ─→ ADR ─→ Implementation
Discussion ───────┘                                        │
                                                           └─ Rejected → заморозка (не ADR)
```

- **Research**: накопление Evidence (Level I–V).
- **Experiment**: проверка hypothesis (KES#3).
- **RFC**: публикуется на обсуждение (статус Draft → Under Review → Decided/Rejected).
- **ADR**: только Decided RFC становится ADR (фиксация).
- **Implementation**: код по ADR (composition root, atomic commit).

---

## RFC Structure (шаблон)

```markdown
# RFC-<NNN>: <Title>
- Author: <name>
- Date: <YYYY-MM-DD>
- Status: Draft | Under Review | Decided | Rejected | Superseded
- Decision Deadline: <YYYY-MM-DD>
- Evidence: <ссылки на ResearchArtifact с evidence_level>

## Summary
<один абзац: что и зачем>

## Context
<текущая ситуация, проблема, ограничения>

## Priorities (ranked)
1. <приоритет> — <почему важно, quantifiable>
2. ...

## Options
### Option A: <name>
- Pros / Cons
- Against priorities: Cost=..., Velocity=...
- Effort: <X weeks> · Risk: Low/Med/High
### Option B: <name>
### Option C: Do Nothing

## Recommendation
<какой option и почему — через priorities>

## Stakeholders
<кого затрагивает>

## Open Questions
<что ещё нужно>

## Review Log
<комментарии ревьюеров, даты>
```

---

## RFC ↔ ADR traceability

- Каждый ADR ссылается на RFC (поле `rfc: RFC-<NNN>` в adrs.yaml).
- Rejected RFC сохраняется в `rfcs.yaml` (статус rejected) — это organisational memory
  (ADR-024 L17): «почему НЕ выбрали X» важнее, чем «почему выбрали Y».
- RFC не нумеруются как ADR (отдельный счётчик, чтобы не смешивать обсуждаемое и принятое).

---

## Честная оценка (Self-Critique RFC)

- **Почему RFC нужен**: gov.uk / Pragmatic Engineer доказали — RFC→ADR handoff устраняет
  «ADR как proposal» (когда proposal И есть ADR, обсуждения не было). KROFT до этого
  прыгал Research→ADR; RFC добавляет human review окно.
- **Риск**: RFC могут стать бюрократией. Митигация: RFC только для значимых решений
  (затрагивающих LAW/слой/платформу). Локальные фичи — прямо в ADR или без.
- **LAW K8**: rfcs.yaml — docs (AKB), НЕ runtime. Только doc-lint/arch-gate читает.
- **Отличие от индустрии**: у нас RFC ещё и несёт Evidence Level (KES#1) — утверждение
  ниже Level III не допускается к Decided (KEH §3 gate).
