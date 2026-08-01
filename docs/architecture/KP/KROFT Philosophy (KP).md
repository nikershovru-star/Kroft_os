---
tags: [kroft, kp, philosophy, worldview, principles, source-of-law]
created: 2026-08-01
author: Hermes (Architecture Intelligence — по principal-review пользователя)
status: v1.0 (foundational, почти никогда не меняется)
position: "ВЫШЕ Vision. KP → Vision → KERA → KEH → KES → AKB → ADR → ... → Runtime"
summary: >-
  KROFT Philosophy (KP) — мировоззрение, из которого РОЖДАЮТСЯ LAW (не наоборот).
  Аналог Unix Philosophy / Zen of Python / Google SRE Principles. Почти никогда не
  меняется (в отличие от Vision). KP-001..007. Каждый KP может породить один или
  несколько LAW K1–K8 (и будущие K9+).
---

# KROFT Philosophy (KP) v1.0

> **Самый верх иерархии.** Выше Vision. KP — мировоззрение, НЕ архитектура. Из KP
> рождаются LAW (не наоборот). Аналоги: Unix Philosophy («small is beautiful»),
> Zen of Python, Google SRE Principles. KP почти никогда не меняется; Vision — может.

---

## Принципы (KP-001 .. KP-007)

### KP-001 — Knowledge > Code
Знания о системе (ADR, паттерны, обоснования, история решений) ценнее самого кода.
Код можно переписать; потерянное знание «почему» — нет. → Рождает: AKB (ADR-022),
Org Memory (ADR-024 L17), Glossary.

### KP-002 — Evidence > Opinion
Инженерное решение опирается на доказательства (Evidence Level I–V, KES#1), а не на
мнение эксперта. Expert opinion (Level V) — только hypothesis. → Рождает: KES,
evidence-gate (KEH §3), Decision Science (KES#4).

### KP-003 — Architecture > Features
Архитектура (структура, границы, законы) важнее отдельных фич. Фича, ломающая
архитектуру, отвергается. → Рождает: KERA (конституция), LAW K3/K8, Governance (L12).

### KP-004 — Small Kernel
Ядро KROFT минимально. Сложность — в сервисах и метаслое, не в runtime. → Рождает:
LAW K1 (Kernel импортирует только contracts), вариант б (ADR-020), Composition Root.

### KP-005 — Composable Systems
Система строится из простых частей с чистыми интерфейсами (Contract-first). → Рождает:
contracts/* (ADR-002), ComponentRegistry (ADR-020), Plugin Pattern (PL2).

### KP-006 — Humans Approve
Применение (apply) и утверждение (approve) требуют человека. Автономность — в
исследовании/предложении, не в применении без контроля. → Рождает: LAW K5/K7,
human-in-the-loop (ADR-024 L16), RFC-слой.

### KP-007 — Everything Measurable
Любое утверждение, решение, компонент подлежит измерению (метрики, benchmark,
experiment). Неизмеримое — неприемлемо для значимых решений. → Рождает: KES#2/#3/#4,
Benchmark Science, Experiment Science, AI Engineering Science.

---

## Как KP порождает LAW (traceability)

| KP | Порождает LAW / механизм |
|---|---|
| KP-001 | AKB, Org Memory, Glossary, KES#10 (Engineering Theory) |
| KP-002 | KES, evidence_levels.yaml, Decision Science, ADR-scoring |
| KP-003 | KERA, LAW K3/K8, Governance (L12), PR-check |
| KP-004 | LAW K1, ADR-020 вариант б, Composition Root, Minimal Kernel |
| KP-005 | contracts/*, ComponentRegistry, Plugin Pattern, Interface Standards |
| KP-006 | LAW K5/K7, RFC-слой, human approve, Gödel-boundary (ADR-024) |
| KP-007 | KES#2/#3/#4/#9, Benchmark/Experiment/AI-Eng Science |

**Важно**: LAW K1–K8 формулируются КАК следствие KP, не как произвол. Новый LAW
(напр. K9 Observability-by-default) должен быть выведен из KP (вероятно KP-007) через
meta-ADR, иначе он — ad-hoc (запрещено по KEH §6).

---

## Честная оценка (Self-Critique KP)

- **Почему KP нужен**: Vision меняется (стратегия), Philosophy — почти никогда. Без KP
  LAW выглядят как «список правил сверху»; с KP — как вывод из мировоззрения. Это
  устраняет вопрос «почему мы вообще соблюдаем K8?».
- **Риск**: KP может стать декларативным лозунгом без связи с LAW. Митигация: таблица
  traceability выше — каждый KP порождает конкретный механизм.
- **Риск раздувания**: ограничен 7 принципами (как Unix/Rules of Simplicity). Новый KP
  — только через meta-ADR + обоснование из практики (не интуиция).
- **Отличие от индустрии**: Unix Philosophy — для ОС; KP — для инженерной ОС ИИ-агентов.
  Адаптация: KP-006 (Humans Approve) специфичен для autonomous-систем (Gödel-boundary).
