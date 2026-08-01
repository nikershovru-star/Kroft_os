---
tags: [kroft, adr, adr-025, multimodal, media-intelligence, knowledge-acquisition, video-understanding]
created: 2026-08-01
author: Hermes (Architecture Intelligence — по предложению пользователя: Media Understanding Layer)
status: proposed
relates_to: [ADR-011, ADR-022, ADR-023, ADR-024, KRM, KERA, PROJECT_CONTEXT_MAP]
ports_added: [IMediaIngestionService, IVideoAnalyzer, ITranscriptExtractor, IFrameAnalyzer, IAudioTranscriber]
laws_affected: [K8, K4, K3]
rfc: RFC-005
summary: >-
  ADR-025 — Multimodal Knowledge Engine (PHASE 6). Добавляет Knowledge Acquisition
  Layer: Text (Web Reader) + Video (Video Agent) + Audio (ASR Agent) → Knowledge Pipeline
  → Knowledge Graph 2.0 → Semantic Memory. Components MK-001..005. Интегрируется в
  KRM (entity-type Media) и Knowledge Graph 2.0 (MediaNode). Не нарушает LAW K8 (живёт
  в services/, НЕ runtime/). Локально: yt-dlp + youtube-transcript-api + Ollama Qwen2.5-VL.
---

# ADR-025 — Multimodal Knowledge Engine (PHASE 6)

> **Status**: proposed. **RFC**: RFC-005 (неявно — предложение пользователя). Расширяет
> KROFT от «читает документы» до «изучает весь интернет-контент» (video/audio/websites/
> code/pdf/images). Вписывается в существующую архитектуру (KRM, Knowledge Graph 2.0,
> services/-слой) без нарушения LAW K1–K8.

---

## 1. Context

KROFT сейчас: Documents → Knowledge Graph. Knowledge Platform (ADR-011) работает с текстом.
Но знания — в видео (YouTube-лекции по архитектуре), аудио (подкасты), PDF, изображениях.
Hermes должен **добывать знания из любых источников** (цель KnowledgeOS).

Прецеденты (исследованы):
- **VideoRAG** (learnopencv): video as knowledge base → VLM captions + ASR → entity-relation
  mapper → per-video sub-graph → global knowledge graph. **Точная архитектура нашего предложения.**
- **arxiv 2510.01513**: Pipeline = DataWindow (video segment + aligned transcript/frames) →
  Pipes (micro-service) → Consumer → VideoKnowledgeBase. **Pipe-архитектура = KROFT Pipeline Pattern PL5.**
- **Multimodal LLM pipelines** (Medium/tutai): Frame Extraction → VLM caption (BLIP/Qwen-VL)
  → ASR (Whisper) → LLM synthesis.

## 2. Decision

Ввести **Knowledge Acquisition Layer** как расширение `services/`:

```
Hermes Agent
    └── Knowledge Acquisition
            ┌────────────┼────────────┐
          Text         Video        Audio
            |            |            |
       Web Reader   Video Agent   ASR Agent
            |            |            |
            └────────────┼────────────┘
                     Knowledge Pipeline
                            |
                     Knowledge Graph 2.0
                            |
                     Semantic Memory
```

**Components (MK-001..005):**
- **MK-001 Video Understanding Service** (`services/media_intelligence/video_analyzer.py`)
- **MK-002 Audio Transcription Service** (`services/media_intelligence/audio_transcriber.py`, Whisper/Ollama)
- **MK-003 Vision Analysis Service** (`services/media_intelligence/frame_analyzer.py`, Qwen2.5-VL via Ollama)
- **MK-004 Media Knowledge Extractor** (`services/media_intelligence/media_ingestion_service.py` — оркестратор Pipeline)
- **MK-005 Multimodal Graph Nodes** (расширение Knowledge Graph 2.0: `MediaNode`, `VideoNode`)

**Ports (contracts/):**
- `IMediaIngestionService` — ingest(url) → KnowledgeGraph
- `IVideoAnalyzer` — analyze_video(url) → VideoDocument
- `ITranscriptExtractor` — get_transcript(video_id) → Transcript
- `IFrameAnalyzer` — analyze_frame(image) → Description
- `IAudioTranscriber` — transcribe(audio) → Transcript

## 3. KRM integration (метамодель)

Добавить entity-types в KRM:
- **Media** (сущность: видео/аудио/изображение/PDF как источник Knowledge)
- **MediaNode** (узел Knowledge Graph 2.0, типизированный Media)

Allowed relationships:
```
Media ──produces──> Knowledge (через Pipeline)
MediaNode ──contains──> Concept
Concept ──implements──> Pattern
Concept ──related_to──> Component
```
Пример после анализа «Building an AI Agent Framework»:
```
VIDEO_NODE(Building AI Agents)
  └─contains─> Agent Architecture
       └─implements─> Planner-Executor Pattern
            └─related_to─> Hermes Runtime
```

## 4. Tech stack (локально, RTX 3060 12GB)

| Задача | Инструмент | Статус |
|---|---|---|
| YouTube metadata | `yt-dlp` | требует `pip install yt-dlp` |
| Субтитры | `youtube-transcript-api` | требует `pip install` |
| Frame vision | `Ollama qwen2.5-vl` | требует `ollama pull qwen2.5-vl` (модель ~4GB) |
| Audio ASR | `Ollama whisper` / `faster-whisper` | требует установку |
| Pipeline | KROFT Pipeline Pattern (PL5) | есть |

**Важно**: внешние вызовы (yt-dlp) — через `adapters/`, НЕ напрямую в services (LAW K6).
Ollama — внешний LLM-адаптер (как OmniRoute), base_url только (LAW K8, tech_catalog).

## 5. Constraints (LAW)

- **K8**: media_intelligence в `services/`, НЕ `runtime/`. Vision/LLM — вне ядра.
- **K4**: VideoDocument/Transcript — frozen + traceable (AgentResult-like).
- **K3**: media_intelligence не импортирует kernel напрямую; через порты.
- **K6**: YouTube/Whisper/Ollama вызываются через `adapters/`, не из services напрямую.

## 6. Consequences

**Плюсы**: Hermes перестаёт быть «читателем файлов» → становится «AI-архивариусом».
Knowledge Graph обогащается мультимодально. Reuse KROFT Pipeline/Supervisor/EventBus.

**Риски (честно)**:
- **YouTube 403/rate-limit**: видео недоступны (как в примере пользователя `watch?v=xxxx`
  → 403). Митигация: graceful fallback на transcript-only, если frames недоступны.
- **Vision noise**: OCR/дублирующие captions (arxiv 2510.01513 warnings). Митигация:
  deduplication + concreteness filter при построении графа.
- **Local VRAM**: Qwen2.5-VL ~4GB на RTX 3060 12GB — ок, но batch ограничен.
- **Преждевременность**: код пишется ПОСЛЕ Варианта Г (unify repo). Сейчас — документ
  + skill (вне repo, даёт capability немедленно).

## 7. Implementation plan (после Варианта Г)

1. `git init` KROFT_OS + перенос кода (Вариант Г).
2. `pip install yt-dlp youtube-transcript-api` + `ollama pull qwen2.5-vl`.
3. `contracts/imedia*.py` (порты).
4. `services/media_intelligence/` (MK-001..005).
5. `adapters/youtube_adapter.py`, `adapters/ollama_vision_adapter.py`.
6. Расширение Knowledge Graph 2.0 (MediaNode).
7. `tests/test_media_intelligence.py` (golden: fake video metadata).
8. MCP tool `mcp__hermes_os__analyze_video` (после появления MCP-слоя).

## 8. Честная оценка (Self-Critique ADR-025)

- **Почему сейчас документ, не код**: KROFT ещё не единый repo (Вариант Г не завершён).
  Писать `services/media_intelligence/` в KnowledgeOS-v5 (скоро archive) = преждевременно.
  Документ + skill — правильный шаг (по паспорту §6 «вперёд: Architecture Gate, затем фичи»).
- **Почему НЕ отдельный «skill для видео»**: ты прав — это Media Understanding Layer,
  единый Acquisition слой, а не разрозненные скиллы. MK-001..005 как под-компоненты.
- **VideoRAG как прецедент**: наша архитектура почти идентична — значит не изобретаем,
  а адаптируем проверенное. KROFT Pipeline Pattern (PL5) = их DataWindow Pipe.
- **LAW K8 соблюдён**: весь Media Layer в services/, vision/LLM через adapters (как OmniRoute).
- **Risk 403**: реальный (yt недоступен без ключа/rate). Skill должен graceful degrade.
