# KROFT_OS

**Autonomous Intelligence Operating System** — модульная операционная система для
построения автономных интеллектуальных систем. Микроядро + платформы ресурсов +
когнитивные сервисы, не привязанные к конкретным моделям ИИ или провайдерам.

> Не «ещё один AI-агент» и не «ещё один framework» — а **операционная система**,
> где интеллект — системный ресурс, как память, ФС или сеть.

## Что это

Интеллект (LLM, Knowledge Graph, Obsidian, OmniRoute и т.д.) — лишь ресурсы ядра,
не основа. Смена стека не устаревает проект.

```
                KROFT_OS
              Operating System
      ┌──────────────┼──────────────┐
  Model Platform  Memory Platform  Knowledge Platform
      ├──────────────┼──────────────┤
              Workflow Platform
              Tool Platform
              Security Platform
            Observability Platform
             Plugin Platform
                Applications
```

Приложения поверх KROFT_OS: MarketMind, Research Assistant, KnowledgeOS, Hermes,
Desktop Assistant, Automation Hub, RAG-системы, корпоративные AI-агенты.

## Документация

- `docs/roadmap/ROADMAP.md` — Master Architecture Roadmap (14 волн, 5 этапов, видение).
- `docs/roadmap/RELEASES.md` — история релизов.
- `docs/Build Journal — Wave 3-9.md` — **журнал сборки**: как это строилось, какие решения
  и в каком порядке принимались, что сломалось по дороге.
- `docs/architecture/ADR-001..012` — архитектурные решения (ядро, контракты, шина
  событий, реестр, модель ресурсов, Model / Policy / Evaluation / Knowledge / Memory Platform).
- `docs/specifications/` — детальные спецификации (Kernel, Scheduler, ResourceManager).

## Статус (2026-07-31)

| Волна | Платформа | Статус |
|-------|-----------|--------|
| 0–2 | Foundation (ядро, шина, контракты) | ✅ |
| 3–4 | **Model + Registry** (ADR-006/033) | ✅ `b06f526` `0edbe24` |
| 5 | **Policy** (ADR-009) + 5.1 Privacy + 5.2 Security | ✅ чек-лист 100% |
| 6 | **Routing** (Router + PolicyEngine + Fallback) | ✅ |
| 7 | **Evaluation** (ADR-010) | ✅ `8461f03` `16443bb` `ee0e396` |
| 8 | **Knowledge** (ADR-011) | ✅ `ca32626` `ba38ee4` `cf453cd` |
| 9 | **Memory** (ADR-012) | ✅ `ce26ac2` `47a8a1f` `fee3086` |
| 10 | **Workflow** (ADR-013) | ✅ `565e4f4` `4f8fc1b` `7e5c2ad` `01780c9` |
| 11–14 | Agent → Autonomous | ⬜ не начаты |

Правило волны 8: *LLM производит гипотезы — граф хранит только проверенные факты.*
Правило волны 9: *тип памяти — это роль (тег), а не отдельный движок.*
Правило волны 10: *задача — это данные (Workflow), не цепочка вызовов; воспроизводимость = детерминированный JSON.*

Тесты волн 5–10: **181 passed, 7 skipped**. Арх-гейт: 0 новых нарушений.

> Примечание: git-репо пока называется `KnowledgeOS-v5` (OS-lock мешает переименовать
> папку); бренд в коде уже `KROFT_OS`.
