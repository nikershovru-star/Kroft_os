---
id: RFC-013
title: "Multimodal Knowledge Engine — Video/Audio/Vision Ingestion (TZ-MULTIMODAL-001)"
status: under_review
date: "2026-08-02"
related: [TZ-MULTIMODAL-001, ADR-041, ADR-025, TZ-AGENT-001, TZ-OBS-001, Stage-26]
authors: [kroft-architect]
evidence_level: III
---

# RFC-013: Multimodal Knowledge Engine

## 0. Research synthesis (2026-08-02)
- **Multimodal RAG backbone** (NVIDIA/Ragie/Elastic): grounding в common
  modality (text). Video = audio→ASR + visual→frame-sampling→Vision LLM, затем
  blend + LLM-synthesize. Key-frame temporal context критичен.
- **Local VLM**: Ollama `qwen2.5vl:7b` (6GB, 125K ctx) — топ local VLM для
  док/чартов. API: `ollama.chat(model, messages=[{role,content,images:[b64]}])`.
  Video frames: multi-frame `fps=1.0`. У нас УЖЕ есть `OllamaAdapter`
  (OpenAI-compatible) — расширяем для vision (НЕ новый adapter).
- **Agent ingestion**: yt-dlp (download) → faster-whisper (transcribe) → LLM.
- **Hexagonal**: Port в core, Adapter на edges (K1/K8).

## 1. Problem
KROFT_OS Knowledge Graph строится из текста (notes/markdown). Video/audio/image
остаются вне графа: лекции, демо, подкасты, скриншоты диалогов — теряются как
источник знаний. LLM-порт `ILlm` — только текст (complete/stream).

## 2. Proposal

### 2.1 Порт `IMultimodalParser` (`contracts/`)
```python
class IMultimodalParser(ABC):
    @abstractmethod
    def parse(self, source: MediaSource) -> MediaKnowledge: ...
@dataclass
class MediaSource:
    kind: str            # "video" | "audio" | "image" | "youtube"
    path: Optional[str]  # local file
    url: Optional[str]   # remote (youtube)
    fps: float = 1.0
@dataclass
class MediaKnowledge:
    text: str                      # grounded common-modality text
    segments: List[MediaSegment]   # timestamped
    metadata: Dict[str, Any]
@dataclass
class MediaSegment:
    t_start: float
    t_end: float
    text: str
    kind: str   # "speech" | "visual"
```

### 2.2 Адаптеры (`adapters/`, optional heavy deps per K8)
- `OllamaVisionAdapter` — расширяет существующий `OllamaAdapter`: добавляет
  `analyze_image(path, prompt)` / `analyze_frames(frames, prompt)` через Ollama
  `qwen2.5vl`. Stdlib + `ollama` (уже есть в deps? проверить). ЗАВИСИТ от
  наличия модели локально — degrade gracefully.
- `YtDlpTranscriptAdapter` — `yt-dlp` (download audio) + `faster-whisper`
  (transcribe). **Optional**: импорт внутри метода (lazy), НЕ в модуль — чтобы
  arch-gate K8 не падал, если dep нет. `MediaIntelligenceService` регистрирует
  адаптер только если dep доступен (composition проверяет `importlib.util`).
- `FrameAnalyzer` — ffmpeg frame sampling (`subprocess`, через IExecutionSandbox!)
  → OllamaVisionAdapter.

### 2.3 `MediaIntelligenceService` (`services/`)
Оркестрирует pipeline (grounding в text):
- video: YtDlpTranscriptAdapter (audio→text) + FrameAnalyzer (visual→VLM→text)
  → blend segments → LLM-synthesize summary → `MediaKnowledge`
- audio: YtDlpTranscriptAdapter → text
- image: OllamaVisionAdapter.analyze_image → text
Интеграция: `MediaKnowledge.text` → Knowledge Graph v2 как **VIDEO_NODE**
(contains→implements→related_to). Reuse GraphQueryEngine + AgentService.

### 2.4 Integration с существующим
| Компонент | Роль |
|-----------|------|
| `ILlm` / `OllamaAdapter` | vision-extension (qwen2.5vl) |
| `IExecutionSandbox` | frame sampling (ffmpeg subprocess) — K8 clean |
| `KnowledgeGraph` (Stage 26) | VIDEO_NODE ingest |
| `AgentService` | tool `ingest_media` маршрутизирует в MediaIntelligenceService |
| `ITelemetrySink` (TZ-OBS-001) | media_ingest.duration, media_ingest.errors метрики |

### 2.5 API (future)
`POST /api/ingest/media` {url/path, kind} → MediaKnowledge + graph nodes.

## 3. LAW Compliance
- **K1**: `IMultimodalParser` + `MediaKnowledge` в `contracts/` (stdlib only).
- **K3**: адаптеры + сервис wire в `composition/`.
- **K5**: тяжёлые deps (whisper/torch/yt-dlp) — только optional adapters, lazy
  import, graceful degrade. Не блокируют core (arch-gate зелёный без них).
- **K6**: сервис → адаптеры через порты.
- **K8**: адаптеры в `adapters/`, сервис в `services/`, НЕ в kernel/runtime.

## 4. Risks
- VRAM: Qwen2.5-VL 7b = 6GB (у нас RTX 3060 12GB ✅). 32b/72b — нет.
- yt-dlp rate-limit → cookies needed; timeout через IExecutionSandbox.
- Whisper accuracy на non-English (ru) — medium model.
- "Common modality" может терять визуальный нюанс — mitigation: сохранять
  `MediaSegment.kind` в графе.

## 5. Validation (при K5 go)
- Тесты `OllamaVisionAdapter` (mock ollama, real только если модель есть)
- Тесты `YtDlpTranscriptAdapter` (lazy import, absent-dep → graceful)
- Тесты `MediaIntelligenceService` (pipeline orchestration, mock adapters)
- Arch-gate: K1/K6/K8 (lazy imports не ломают gate)
- Suite target: +12 tests

## 6. Alternatives
- Cloud VLM API (GPT-4V) — отвергнуто (local-first мандат KROFT)
- Unified multimodal embedding — отложено (сложно, нет local embedder)
- Интеграция в `ILlm` напрямую (multimodal_complete) — рассмотрено, НО
  MediaIntelligenceService имеет свой pipeline (ASR+VLM+blend) → отдельный порт
  `IMultimodalParser` чище, чем раздувать `ILlm`.
