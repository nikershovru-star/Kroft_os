---
id: RFC-021
title: "AI Marketplace — registries, packages, versioning, compatibility (TZ-021)"
status: under_review
date: "2026-08-02"
related: [TZ-021, ADR-050, TZ-AGENT-001, ADR-045, ADR-047, WP-14]
authors: [kroft-architect]
evidence_level: III
---

# RFC-021: AI Marketplace (TZ-021)

## 0. Research synthesis (2026-08-02) — см. ADR-050 §2
AI Agent Marketplace 2026; Skilldex arxiv 2604; VS Code plugin arch; SemVer 2.0.

## 1. Problem
Другие люди не могут подключаться: нет registries, packages, versioning, compat.
KROFT_OS не распространяема.

## 2. Proposal — 8 components

### 2.1 `IPackageRegistry` (`contracts/`)
```python
class IPackageRegistry(ABC):
    def publish(self, pkg: PackageManifest) -> None: ...
    def resolve(self, name: str, ver_range: str) -> Optional[PackageManifest]: ...
```
PackageManifest: name, version (SemVer), deps, source (url/github pin), type.

### 2.2 `IPluginRegistry` (`contracts/`)
```python
class IPluginRegistry(ABC):
    def register_plugin(self, plugin: PluginManifest) -> None: ...  # pinned source
    def compatible(self, runtime: str) -> List[PluginManifest]: ...
```

### 2.3 `IAgentRegistry` (`contracts/`)
```python
class IAgentRegistry(ABC):
    def publish_agent(self, spec: dict) -> None: ...   # reuse IAgentPlatform specs
```

### 2.4 `IWorkflowRegistry` (`contracts/`)
```python
class IWorkflowRegistry(ABC):
    def publish_workflow(self, graph: TaskGraph) -> None: ...   # reuse ADR-045
```

### 2.5 `IMemoryPackage` / `IKnowledgePackage` (`contracts/`)
```python
class IKnowledgePackage(ABC):
    def export(self, selector: dict) -> bytes: ...   # reuse ADR-047 KG subset
    def import_pkg(self, data: bytes) -> None: ...
```

### 2.6 `IVersioning` (`contracts/`)
```python
class IVersioning(ABC):
    def parse(self, v: str) -> tuple: ...   # SemVer 2.0
    def satisfies(self, v: str, range: str) -> bool: ...
```

### 2.7 `ICompatibility` (`contracts/`)
```python
class ICompatibility(ABC):
    def check(self, pkg: PackageManifest, runtime: str) -> bool: ...  # dep ranges
```

### 2.8 `MarketplaceService` (`services/`)
Install/resolve packages; distributed registry via ICrdtGraph (TZ-022 federation-ready).
Reuse ICrdtGraph (WP-14) + IAgentPlatform (TZ-AGENT-001) + ILlm.

## 3. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: install requires human/K5 approval (external code); signature verify.
- **K6**: через ICrdtGraph/IAgentPlatform порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- Supply-chain: unverified packages — mitigate: signature verify + K5 approval.
- Version conflicts — SemVer range resolution.

## 5. Validation (при K5 go)
- registries publish/resolve; SemVer parse/satisfies; compat check; install resolves
  deps; knowledge package export/import. No auto-exec of unverified code.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Centralized npm-like server — отвергнуто (SPOF, not local-first); CRDT registry.
- No versioning — отвергнуто (dependency hell).
