---
tags: [kroft, keh, research-handbook, methodology]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KEH
summary: "Research Handbook (KEH) — процесс исследований + evidence-gate. Ссылается на KES Research Science."
---

# KEH — Research Handbook

> Handbook KEH: как проводить исследования в KROFT. Выведен из KP-002 (Evidence > Opinion).

## Процесс (Research Loop, EIP)
1. Research Mesh агенты собирают источники (ADR-023).
2. Каждый источник → ResearchArtifact с `evidence_level` (KES Research Science).
3. Synthesizer (RAG over AKB) консолидирует; требует `consensus ≥ 2`.
4. Результат → AKB (`research/`) + Knowledge Loop.

## Evidence Gate (KEH §3)
| Level | Допустимо для |
|---|---|
| I (systematic) | Фундаментальный LAW/паттерн |
| II (empirical) | Выбор реализации |
| III (comparative) | Локальное решение |
| IV (case) | Post-mortem |
| V (expert/blog) | ТОЛЬКО hypothesis |

ADR требует min Level III + consensus≥2. Ниже → «proposed-low-confidence».

## Fresh-source acquisition (Firecrawl / managed web tools)
Перед любым research-шагом (L1) свежие источники тащатся через managed web tools
(Firecrawl, входящий в Nous-подписку Hermes) — НЕ через устаревшие базлайны ТЗ и НЕ
через память-в-сообщении. Конкретно:
1. Для каждого утверждения в ТЗ/ADR ищем ≥2 независимых live-источника (GitHub код,
   eng-blog Google/DeepMind/Anthropic/Netflix/Uber/Cloudflare/Hashicorp/Temporal/RedHat/
   Datadog, RFC/ADR, офиц. документация). Cross-domain (ОС/Distributed/Actor/Game/Browser/
   DB/Infra) обязателен.
2. `web_extract` по офиц. документации библиотек = замена внешнему context7-MCP
   (in-process, без отдельного сервера).
3. Результат каждого источника → `ResearchArtifact` с `evidence_level` (см. ниже);
   синтез требует `consensus >= 2`.
4. Питает AKB (`research/`) и Knowledge Loop. LAW K8 соблюдён: сбор — в services/docs,
   НЕ в runtime/ kernel/.

## Запрещено
Утверждение на основе одного блога (Level V) без пометки «hypothesis».
Использование устаревшего базлайна ТЗ как единственного источника (KROFT OS: базлайны
ТЗ систематически врут — требуется K5-разведка свежими источниками).

## Честная оценка
Evidence-Based SE доказал: hierarchy снижает bias. KROFT применяет к инженерным решениям.
Gate только для ADR-уровня (не бюрократия на каждую строку). LAW K8: AKB в docs/.
