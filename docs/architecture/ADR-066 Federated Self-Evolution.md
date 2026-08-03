---
id: ADR-066
title: "Federated Self-Evolution — what of the SOFT layer to federate (ТЗ-FSE-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.85
confidence: high
risk: low
related: [ADR-044, ADR-054, ADR-062, ADR-063, ADR-064, ADR-065, TZ-015, NW-01, SE-01, ME-01, I-08, I-10]
addresses: [TЗ-FSE-01, O1, K1, K6, K8]
---

## 1. Context
SE-01 замкнул ЛОКАЛЬНУЮ петлю самоэволюции (исходы -> эволюция -> поведение). NW-01 дал
реальную федерацию WorldState. Но эволюционировавший SOFT-слой (semantic facts +
soft policies) НЕ федерируется: узел, выучивший avoid-политику, не делится ею; пир без
опыта неуспеха продолжает наступать на те же грабли. Финальная цель («локально и в
сети») требует КОЛЛЕКТИВНОГО ОБУЧЕНИЯ: выученное распространяется и меняет поведение
каждого узла. ТЗ-FSE-01 — кульминация двух столпов (NW-01 + SE-01).

## 2. Decision — что федерировать (явное, не импровизированное)
SOFT-слой живёт в `ILayeredMemory` (НЕ WorldState — отдельный канал). Решение о
федерации КАЖДОГО вида знания:

| Вид знания | Федерировать? | Условие / гейт | Обоснование |
|---|---|---|---|
| **Semantic facts** (`decided:X`) | **ДА** | confidence >= порога | Знания общего характера; полезны всем узлам (коллективная норма). |
| **Soft policies** (`avoid:X` / `prefer:X`) | **ДА** | `layer=="soft"` И confidence >= порога И provenance сохраняется | Поведенческие уроки; полезны, но требуют доверия к источнику. |
| **HARD layer** (нормы/контракты/FSM) | **НИКОГДА** | — | O1: HARD immutable, не эволюционирует и не федерируется. Это граница безопасности. |

**Гейты (двойная защита — sender И receiver):**
- **Confidence-гейт**: слабые уроки (низкая aggregated confidence) НЕ рассылаются и
  НЕ принимаются. Параметр `confidence_threshold` (по умолчанию 0.5) на обеих сторонах.
- **Provenance-гейт**: каждый элемент несёт `origin` (узел-источник). Receiver сохраняет
  provenance — узел знает, ЧЬИМ опытом он теперь руководствуется (аудит + отзыв).
- **Dedup по content/body**: повторные рассылки идемпотентны (causal merge).
- **HARD rejection**: `layer != "soft"` на sender отбрасывается; на receiver — доп.
  страховка (O1 guard).

**Транспорт:** переиспользуется NW-01 `INetworkTransport` (расширен вторым каналом
`send_soft_layer`/`on_soft_layer`, топик `cog.soft`). НЕ создаём новый транспорт.

## 3. Architecture (коллективное обучение)
```
[Node A] Learn-фаза -> ILayeredMemory(soft: avoid:X, conf=0.8, origin=A)
    |  FederationSoftMemorySync.publish_soft_layer(memory, threshold, 'A')
    v  INetworkTransport.send_soft_layer([SoftLayerItem...], 'A')  -- cog.soft
[Network]
    v  INetworkTransport.on_soft_layer(handler)
[Node B] FederationSoftMemorySync._on_remote_soft(items, 'A')
    |  merge в ILayeredMemory B (dedup + confidence-гейт + provenance сохранён)
    v  MemorySoftPolicySource(B) читает avoid:X  ->  PolicyAwareValueSystem штрафует X
[Node B] СЛЕДУЮЩИЙ tick ИЗБЕГАЕТ X (без локального опыта неуспеха)
```
Read-side (SE-01) НЕ меняется: `MemorySoftPolicySource`/`KnowledgeAwareReasoning` уже
читают `ILayeredMemory`. Федерация только НАПОЛНЯЕТ слой.

## 4. Capstone proof (tests/test_federated_self_evolution.py, K8)
- **CAPSTONE**: A repeatedly FAIL по X -> учит avoid X (conf>=порога) -> федерация ->
  B (БЕЗ опыта неуспеха) ИЗБЕГАЕТ X.
- **NEGATIVE**: без федерации B НЕ избегает X (доказывает, что причина — федерация).
- **Confidence-гейт**: low-confidence урок НЕ федератируется (ни sender, ни receiver).
- **O1**: HARD НЕ федератируется; provenance origin сохраняется.
- Существующие NW-01/SE-01 тесты НЕ сломаны.

## 5. Relationship to O1 / K1 / K6 / K8 / I-08 / I-10
- **O1**: HARD никогда не федерируется/мутируется; гейты enforced на sender+receiver.
- **K1**: contracts+stdlib; `FederationSoftMemorySync` в services (зависит от портов).
- **K6**: federation зависит от `INetworkTransport` порта, НЕ от конкретного адаптера.
- **K8**: negative (без фед. B не избегает) + confidence-гейт обязательно тестируются.
- **I-08** (federated projection): SOFT-слой — вторая federated projection (рядом с
  WorldState). **I-10** (kernel purity): LLM-free core сохранён (федерация знаний, не
  моделей).

## 6. Constraints / Non-scope
- Реальные LLM/agent-адаптеры; RL; multi-agent оркестрация (ТЗ-AGENT закрыт) — не
  переоткрывать.
- Консенсус/глобальная согласованность норм (Raft для норм) — future; здесь causal
  merge + confidence-гейт (достаточно для reference).
- **Урок Флага 1 LLM-01**: все VOs (SoftLayerItem) — ЗАМОРОЖЕННЫЕ, НЕ duck-objects.
- **Урок Флага 2 LLM-01**: перед созданием модуля/docs — проверка реального дерева и
  уникальности якоря.

## 7. Test Stability (honest note)
Тесты K8 детерминированы. Используется реальный `NetworkTransport` (localhost TCP,
как в NW-01) для капстоуна A->B; confidence-гейт/negative — in-process (без сети).
`--count=5` не требовался для in-process; сетевой капстоун — единичный (детерминирован
по ТЗ-NW-01 принципу).

## 8. Future Work
- RaftLite для согласованности норм (consensus на SOFT-слое).
- Weighted federation: узлы с высоким trust-score дают больший вес чужим урокам.
- Substring-matching политик (ADR-064 §8) — задок-долг, влияет и на федерированный
  слой.
