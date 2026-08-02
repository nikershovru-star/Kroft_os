---
id: ADR-050
title: "AI Marketplace — registries, packages, versioning, compatibility (TZ-021)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.80
confidence: high
risk: medium
related: [TZ-021, TZ-AGENT-001, ADR-045, ADR-047, WP-14, Wave-3]
---

# ADR-050: AI Marketplace (TZ-021)

## 1. Context
Теперь другие люди смогут подключаться. TZ-021 добавляет: Package Registry, Plugin
Registry, Agent Registry, Workflow Registry, Memory Packages, Knowledge Packages,
Versioning, Compatibility. KROFT_OS становится распространяемой платформой.

## 2. Research Synthesis (2026-08-02)
- **AI Agent Marketplace 2026**: "App Stores for plugins" — distribution layer для
  agent capabilities; cross-agent compat через open standards (SKILL.md open standard
  — мы уже используем SKILL.md для skills!).
- **Skilldex** (arxiv 2604): Package Manager + Registry для Agent Skill Packages с
  hierarchical scope-based distribution; versioning = open question.
- **Plugin Architecture** (VS Code / Chris Ayers): marketplace.json registry,
  plugin.json (version + pinned source github URL), cross-tool compat dirs.
- **Semantic Versioning 2.0** (semver.org): X.Y.Z immutable, backward-compat rules.
  Gold standard для Versioning.

## 3. Decision
Порты в contracts (K1), сервисы в services (K8). Reuse ICrdtGraph (WP-14) для
distributed registry + TZ-AGENT-001 (agent specs) + ADR-045 TaskGraph (workflows) +
ADR-047 (knowledge packages):
- `IPackageRegistry` — package(name, version, deps, source) metadata store.
- `IPluginRegistry` — plugin registry (pinned source, compatible runtime).
- `IAgentRegistry` — agent packages (reuse IAgentPlatform specs).
- `IWorkflowRegistry` — workflow packages (reuse ADR-045 TaskGraph).
- `IMemoryPackage` / `IKnowledgePackage` — memory/knowledge bundles (reuse ADR-047).
- `IVersioning` — SemVer 2.0 compliance (parse, compare, immutable releases).
- `ICompatibility` — runtime/dep compat check (version ranges, min runtime).
- `MarketplaceService` — install/resolve packages; distributed via ICrdtGraph (TZ-022
  federation-ready). Reuse ICrdtGraph + ILlm + IAgentPlatform.

## 4. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: install requires human/K5 approval (external code → risky); signature verify.
- **K6**: через ICrdtGraph/IAgentPlatform порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
Author ──publish──▶ Marketplace (registries + versioning)
User   ──install──▶ resolve compat ──▶ load plugin/agent/workflow/knowledge
```

## 6. Validation (когда K5 go)
- package/plugin/agent/workflow/memory/knowledge registry; SemVer parse/compare;
  compat check (range); install resolves deps. No auto-exec of unverified code.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-021 (TZ-021); AI Agent Marketplace 2026, Skilldex arxiv 2604, VS Code plugin
  arch, Semantic Versioning 2.0 (semver.org)
- WP-14 (ICrdtGraph), TZ-AGENT-001, ADR-045 (TaskGraph), ADR-047 (World/KG)
