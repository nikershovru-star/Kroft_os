---
tags: [kroft, keh, documentation-handbook, standards, glossary]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KEH
summary: "Documentation Handbook (KEH) — стандарты документации + Glossary (KL). Ссылается на KES Human Factors."
---

# KEH — Documentation Handbook

> Handbook KEH: как писать документацию. Выведен из KP-001 (Knowledge > Code). Связан с KL/Glossary.

## Стандарты
1. ADR = MADR-подобный: Context → Decision → Consequences → Evidence → Tradeoffs.
2. KERA/KES/KEH = верхнеуровневые; ADR = точечные; AKB = данные. Не смешивать.
3. Каждый документ достижим из MOC (KMP §7 Single Source of Truth).
4. Документы для людей + машинночитаемый индекс (AKB YAML).
5. Neobrutalist style (Unbounded/Hanken/Space Mono) для читаемости (Human Factors, KES#8).

## Glossary (KL) enforcement
- Только термины KL (`akb/glossary.yaml`). Синонимы из `aliases` — запрещены.
- doc-lint при PR флагует устаревший/не-KL термин.
- Новый термин → сначала в KL (meta-ADR), потом использование.

## Честная оценка
DDD ubiquitous language устраняет перевод между стейкхолдерами. В KROFT (Hermes+люди+агенты)
критично: агенты понимают термины однозначно (снижает галлюцинации, KES#9). LAW K8: AKB docs/.
