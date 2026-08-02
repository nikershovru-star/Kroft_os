---
id: ADR-042
title: "Architecture Intelligence Services — L5 Simulator, L6 Tech Debt, L7 Evolution (WP-12)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.84
confidence: high
risk: low
related: [TZ-AGENT-001, TZ-OBS-001, ADR-041, ADR-038, Wave-3]
---

# ADR-042: Architecture Intelligence Services (WP-12)

## 1. Context
Wave 3 STARTED (ADR-041). Мои architect-skills (research-before-code, ADR-lifecycle,
cross-domain analysis) работают как внешние Hermes-скиллы, НЕ как KROFT-нативные
компоненты. По Architecture Intelligence Protocol v2.0 (L5/L6/L7) эти способности
должны быть runtime-сервисами, переиспользующими AKB (machine-readable YAML).
TZ-OBS-001 дал ITelemetrySink (circuit.trip / drift.score метрики) — топливо для L7.

## 2. Decision
Формализовать 3 сервиса в `services/architecture_intelligence/` (K8), порты в
`contracts/` (K1), reuse AKB (НЕ runtime-код, LAW K8):
- **L5 Simulator** (`IChangeSimulator`): симуляция изменений перед коммитом.
  Dry-run via IExecutionSandbox (напр. `python -m py_compile`, import-check) +
  arch-gate preview (K1/K8 axis check) без реального применения. Возвращает
  predicted violations.
- **L6 Tech Debt Engine** (`ITechDebtAuditor`): авто-аудит архдолга по AKB
  (laws.yaml violated?, adrs stale?, import_matrix breaches) + метрики (drift.score,
  circuit.trip rate) → DebtReport со score + items.
- **L7 Evolution Engine** (`IEvolutionPlanner`): генерация roadmap из drift trends
  (SelfAnalyzer) + circuit trip / sandbox kill trends (ITelemetrySink) + AKB history
  → предложения по рефакторингу (ADR-предложения).

## 3. Consequences
**Positive:** архитектурный интеллект — часть системы (не только в Hermes-скиллах);
self-improving loop (drift→debt→roadmap→KB update).
**Negative:** сервисы читают AKB (файлы) — нужен path к AKB; ленивый reload.
**Risk:** L5 симуляция неточна (static import-check ≠ runtime) — честно помечаем
как predictive, не guarantee.

## 4. Validation (при K5 go)
- Тесты L5 (simulate import-check catches bad import), L6 (debt from AKB + metrics),
  L7 (roadmap from drift history). Negative proof-of-fire (K1/K8).
- Arch-gate unchanged (14). akb-lint PASSED.

## 5. References
- ADR-041 (Wave 3), TZ-OBS-001 (ITelemetrySink), ADR-038 (Supervisor recovery)
- AKB: laws.yaml, adrs.yaml, history.yaml, import_matrix.yaml, tech_catalog.yaml
- kroft-architecture-intelligence skill (curator-owned, переиспользуется как источник)
