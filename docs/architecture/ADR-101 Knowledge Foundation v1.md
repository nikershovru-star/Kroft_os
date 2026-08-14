---
tags:
  - architecture_decision_record
  - knowledge_foundation
  - kroft_os
---

# ADR-101: Knowledge Foundation v1 — база первоисточников KROFT

- **Статус:** Принято (2026-08-07)
- **Контекст:** Пользователь предложил список из ~68 фундаментальных книг
  (философия, логика, математика, теория информации, AI, ОС, архитектура,
  распред. системы, БД/КГ, когнитивистика, теория управления, методология)
  как ядро «сознания» KROFT. Решено не загружать всё сразу, а собрать
  **Knowledge Foundation v1** из ~15 ключевых источников + дать легальные
  ссылки на свободный доступ.
- **Решение:**
  1. Структура каталогов `KROFT_KNOWLEDGE_FOUNDATION/` (13 разделов).
  2. Ядро v1 = 15 книг (см. ниже).
  3. Конвейер инgestа: SOURCE→DOCUMENT→CHUNKS→CONCEPTS→KNOWLEDGE NODES→
     RELATIONS→SEMANTIC INDEX→KNOWLEDGE GRAPH.
  4. Типы узлов: FACT/CONCEPT/PRINCIPLE/METHOD/DEFINITION/ARGUMENT/EXAMPLE/
     QUESTION/CONNECTION/SOURCE.
  5. Отдельный слой LLM/Transformers/Agents/RAG/Memory — как следующий этап
     (фундамент выше почти не покрывает современную LLM-архитектуру).

## Юридическая граница (важно)
- **Public domain / выложено авторами** — качать легально: Аристотель,
  Платон, Декарт, Бэкон, Юм, Кант, Рассел, Шеннон (статья), Винер, фон Нейман
  (статьи), Ньюэлл&Саймон (препринты), Поппер, Кун, Лакатос, Фейнман, Саган,
  Кантор, Пойа.
- **Современные (под копирайтом)** — только легальные drafts/препринты/авторские
  выкладки (Norvig PAIP, Sutton&Barto RL, Bishop PRML, Kleppmann DDIA draft,
  Evans DDD draft, Lamport статьи). Полные PDF с пиратских лежат вне закона —
  НЕ даю и не качаю.

## Структура каталогов
```
KROFT_KNOWLEDGE_FOUNDATION/
├── 01_logic/
├── 02_philosophy/
├── 03_mathematics/
├── 04_information_theory/
├── 05_ai/
├── 06_cognition/
├── 07_computer_science/
├── 08_software_architecture/
├── 09_distributed_systems/
├── 10_databases/
├── 11_knowledge_graphs/
├── 12_control_systems/
└── 13_scientific_method/
```

## Ядро v1 (15 источников) + легальные ссылки
См. `docs/architecture/AKB/knowledge_foundation_v1.yaml` (машинно-читаемый
каталог ссылок). Там же — разбивка по 13 разделам для остальных ~53 книг.

## Free/Open-access зеркала (проверено 2026-08-07)
- archive.org — PD-классика (Bacon Novum Organum и др.)
- author pages: incompleteideas.net (Sutton&Barto RL), norvig.com/paip-lisp,
  microsoft.com (Bishop PRML), monoskop.org (Wiener, Simon)
- Stanford Encyclopedia of Philosophy — Поппер/Кант (обзоры)
- Cambridge/OUP open chapters — Поппер Logic of Scientific Discovery (PDF)
- GitHub mirrors — Kleppmann DDIA, Evans DDD (raw PDF)

## Реализация (следующий шаг, отдельная волна)
- Скрипт `scripts/fetch_foundation.py`: скачивает по белому списку URL из YAML
  в `KROFT_KNOWLEDGE_FOUNDATION/<section>/`, НЕ трогая копирайт-источники.
- Ingestion-пайплайн (ADR-091 Knowledge Engine) строит КГ из чанков.
- AKB-узлы FACT/CONCEPT/... читаются arch-gate (LAW K8: не импортируется в runtime).
