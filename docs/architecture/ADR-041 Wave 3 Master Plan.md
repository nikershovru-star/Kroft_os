---
id: ADR-041
title: "Wave 3 Master Plan — Multimodal, Distributed Runtime, Hermes v2 Evolution"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.80
confidence: high
risk: medium
related: [TZ-MULTIMODAL-001, ADR-025, TZ-AGENT-001, TZ-OBS-001, Wave-2]
---

# ADR-041: Wave 3 Master Plan

## 1. Context
Wave 0/1/2 закрыли: repo, CI, gate, Knowledge Graph v2 (TZ-KNOW-001), Agent
Platform (TZ-AGENT-001), Supervisor/Recovery (WP-10), Execution Sandbox
(TZ-EXECUTION-001), Observability (TZ-OBS-001). PROJECT_STATUS (`Wave 3 | WP-12
Arch Intelligence, WP-13 Multimodal | ⏸ pending`). ADR-025 (Multimodal) deferred
сюда. Следующий крупный этап эволюции KROFT_OS.

## 2. Wave 3 Scope (3 workstreams)
1. **WP-12 — Architecture Intelligence** (частично DONE: AKB YAML, skills,
   kroft-architecture-intelligence). Цель: L5 Simulator + L6 Tech Debt Engine +
   L7 Evolution Engine как KROFT-нативные services (reuse AKB).
2. **WP-13 — Multimodal Knowledge Engine (TZ-MULTIMODAL-001)** — ADR-025.
   Media Understanding Layer: video/audio/vision → Knowledge Graph. Local-first
   (Ollama Qwen2.5-VL, faster-whisper), optional heavy deps per K8.
3. **WP-14 — Distributed Runtime (Phase G)** — multi-node agent execution,
   consensus, sharding Knowledge Graph. Отдельный ТЗ (после WP-13).

## 3. Research Synthesis (2026-08-02, world practices)
- **Multimodal RAG** (NVIDIA/Ragie/Elastic): лучший backbone = grounding в
  common modality (text). Video = audio→ASR + visual→frame sampling→Vision LLM,
  затем blend + LLM-synthesize. Key-frame temporal context критичен.
- **Local VLM** (Ollama Qwen2.5-VL 7b, 6GB, 125K ctx): топ local для док/чартов;
  Ollama API `images=[base64]`; video frames multi-frame `fps=1.0`. У нас уже
  есть OllamaAdapter (OpenAI-compatible) — расширяем для vision.
- **Agent media ingestion**: yt-dlp (download) → faster-whisper (transcribe) →
  LLM (summarize). Стандартный local pipeline.
- **Hexagonal**: Port в core, Adapter на edges (наш K1/K8).

## 4. Decision
Wave 3 исполняется по ТЗ (K5: research→design ADR→approval→code). Первый ТЗ =
**TZ-MULTIMODAL-001** (WP-13), design в RFC-013. Multimodal = extension текущего
ILlm порта (добавить multimodal-методы) + новые optional adapters + MediaIntelligenceService.

## 5. Consequences
**Positive:** KROFT_OS понимает video/audio/image → богаче Knowledge Graph.
**Negative:** тяжёлые deps (torch/whisper/yt-dlp) — only via optional adapters.
**Risk:** VRAM (Qwen2.5-VL 7b = 6GB) — требует наличия GPU (у нас RTX 3060 12GB ✅).

## 6. References
- RFC-013 (TZ-MULTIMODAL-001 design)
- ADR-025 (Multimodal, deferred)
- NVIDIA Multimodal RAG blog, Ragie pipeline, Ollama Qwen2.5-VL docs
- TZ-AGENT-001 (agent substrate reuse), TZ-OBS-001 (telemetry hooks)
