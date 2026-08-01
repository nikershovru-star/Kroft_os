---
title: "Architecture Gate Coverage Report (WP-02, TZ-001)"
version: "1.0"
date: "2026-08-02"
status: "active"
generated_by: "tests/test_architecture.py + tests/test_architecture_negative.py"
---

# Architecture Gate Coverage Report

> Сгенерировано после WP-02 (расширение arch-gate). Источник матрицы импортов:
> `AKB/import_matrix.yaml` (single source of truth). Negative-тесты в
> `tests/test_architecture_negative.py` доказывают, что каждый детектор срабатывает.

## Автоматически проверяемые (блокирующие)

| Закон | Детектор | Negative-тест | Статус |
|-------|----------|---------------|--------|
| **K1** | `test_no_forbidden_cross_layer_imports` (kernel→infra/services/adapters/policies) | `test_negative_k1_kernel_imports_infra` | ✅ AUTOMATED |
| **K3** | `test_wiring_only_in_composition` (kernel/runtime/services/policies не инстанцируют DependencyContainer/SnapshotStore) | `test_negative_k3_kernel_instantiates_container` | ✅ AUTOMATED |
| **K6** | `test_no_forbidden_cross_layer_imports` (adapters→policies) + `ALLOWED["adapters"]={contracts}` | `test_negative_k6_adapters_imports_policies` | ✅ AUTOMATED |
| **K8** | `test_kernel_runtime_no_ai_imports` (kernel/runtime → akb/research/llm) | `test_negative_k8_kernel_imports_ai` | ✅ AUTOMATED |
| **F1** | `test_no_blocking_sleep_in_recovery` (runtime/recovery, runtime/supervisor) | `test_negative_f1_recovery_blocking_sleep` | ✅ AUTOMATED |
| **F2** | `test_no_forbidden_cross_layer_imports` (runtime→services) | (входит в K1-детектор) | ✅ AUTOMATED |
| **F3** | `test_no_forbidden_cross_layer_imports` (kernel→services) + K3 | (входит в K1/K3) | ✅ AUTOMATED |
| **F4** | `test_kernel_runtime_no_ai_imports` | (входит в K8) | ✅ AUTOMATED |

## Автоматически проверяемые (НЕ блокирующие — warn)

| Закон | Детектор | Статус |
|-------|----------|--------|
| **F5** | `test_agent_result_frozen` — AgentResult ДОЛЖЕН быть frozen dataclass (если присутствует) | ✅ PARTIAL (skip если AgentResult нет; fails если не frozen) |
| **F6** | `test_all_adrs_have_evidence` — ADR в `adrs.yaml` ДОЛЖЕН иметь `evidence_level` | ⚠ PARTIAL (non-blocking warn; полное закрытие = WP-08) |

## НЕ проверяется автоматически (требует ручного review)

| Закон | Причина | Митигация |
|-------|---------|-----------|
| **K2** | «Расширение только через порты» — семантическое, не AST-ловимое | Code review; порты в `contracts/` |
| **K4** | «frozen + traceable вывод» — частично F5; общий trace требует рантайм-проверки | F5 детектор + review Artifact-сериализации |
| **K5** | «Humans Approve» — процесс, не код | Git-дисциплина, запрет push/force |
| **K7** | «Атомарные коммиты, нет git add -A» — процесс | Pre-commit hook (WP-05) |

## Метрики (цель TZ-001 §6)

| Метрика | Baseline (01.08) | После WP-02 |
|---------|------------------|------------|
| Негативных тестов гейта | 0 | **6** (K1, K3, K6, K8, F1 + positive sanity) |
| Законов с авто-проверкой | не определено | K1, K3, K6, K8 (блокирующие) + F5, F6 (warn) |
| Тесты гейта | 3 | **8** (test_architecture.py) + 6 (negative) |
| Известных открытых нарушений | 1 (V3, уже закрыто в Phase C) | **0** |

## Negative-test доказательство

Каждый детектор имеет фикстуру-нарушение в `tests/fixtures_violations/` и
negative-тест, который断言 детектор НАШЁЛ нарушение. Это исключает сценарий
«зелёный гейт при реальном нарушении» (критическая находка TZ-001 §1.1).
