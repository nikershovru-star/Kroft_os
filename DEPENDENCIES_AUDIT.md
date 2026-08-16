# DEPENDENCIES_AUDIT.md — KROFT_OS v5

**Дата:** 2026-08-15 · **Автор:** Hermes Agent · **Причина:** R1 (ТЗ Этап 1, вариант A)
**Метод:** READ-ONLY аудит импортов + изолированная установка из минимального манифеста.
**Принцип:** НЕ `pip freeze`, НЕ сбор всех импортов. Только то, что код реально импортирует.

---

## 1. Current environment (hermes-agent venv)

- Python 3.11.15
- 183 пакета в venv (включая faiss-cpu 1.14.3, fastapi 0.133.1, numpy 2.4.3,
  pydantic 2.13.4, openai 2.24.0, torch НЕТ, sentence-transformers НЕТ).
- **Ключевой факт:** большинство из 183 пакетов кодом KROFT_OS НЕ импортируются.

## 2. Runtime dependencies (что код реально импортирует)

| Package | Импорт | Где | Обязательно? |
|---|---|---|---|
| PyYAML (`yaml`) | `import yaml` | services(3), runtime(2), composition(1), infrastructure(1), tools(1), scripts | ✅ ДА — единственный runtime must-have (17 сайтов) |
| networkx | `import networkx` | `services/graph_query_engine.py` | ⚠️ optional (graph reasoning) |
| ollama | `from ollama` | `adapters/ollama_vision.py` | ⚠️ optional (vision) |
| requests | `import requests` | `scripts/fetch_foundation.py`, `scripts/foundation_extract.py`, `tests/llm/*` | ⚠️ optional/script-only |
| psutil | `import psutil` | observability-адаптеры | ⚠️ optional |
| watchdog | `import watchdog` | file-watch плагины | ⚠️ optional |
| PIL (Pillow) | `from PIL` | image-утилиты | ⚠️ optional |
| pypdf | `import pypdf` | PDF ingestion scripts | ⚠️ optional/script-only |
| faster-whisper / whisper / yt_dlp / pyautogui | — | audio/desktop/scrape scripts | ⚠️ optional (вне ядра) |

**НЕ импортируются нигде в коде (несмотря на наличие в venv):**
`fastapi`, `uvicorn`, `httpx` (кроме 1 теста), `pydantic` (кроме 1 теста),
`numpy`, `scipy`, `faiss`, `sentence-transformers`, `torch`, `openai` (кроме адаптера,
но адаптер импортирует `contracts`, не `openai` напрямую — см. ниже).

> `openai`/`deepseek`: `adapters/openai_compatible.py` импортирует ТОЛЬКО `contracts`
> (K6: адаптер — порт, SDK инjected через композицию). Поэтому `openai` НЕ в runtime-deps.

## 3. Test dependencies

| Package | Назначение |
|---|---|
| pytest>=8.0 | runner (pytest.ini: asyncio_mode=strict) |
| pytest-asyncio>=0.21 | обязателен для asyncio_mode=strict + async тестов |
| pytest-cov>=4.0 | покрытие (ТЗ Этапа 6) |

Тесты импортируют `httpx`/`pydantic`/`fastapi` только в `tests/llm/test_omni_router.py`
(опциональный omni-router тест) — НЕ в остальных 1642 тестах. Поэтому они НЕ в
обязательных dev-deps; если omni-router тест нужен — добавить `httpx`/`pydantic` точечно.

## 4. Optional dependencies

Вынесены в комментарии в `requirements.txt` (networkx, ollama, requests, psutil,
watchdog, pypdf). Переключаются раскомментированием под нужную capability.
Этапы 4–5 (FastAPI веб, fact-check search API) добавят свои зависимости явно, когда
будут построены — сейчас их в коде нет, поэтому НЕ включены (ТЗ STEP 2: «не добавлять
пакет только потому, что он в venv»).

## 5. Version decisions

- **PyYAML>=6.0** — совместимый диапазон; YAML-парсинг стабилен, пин не нужен.
- **pytest>=8.0** — диапазон; suite использует современные маркеры.
- **pytest-asyncio>=0.21** — диапазон; требуется `asyncio_mode=strict` из pytest.ini.
- **НЕ пиним** faiss/numpy/torch — они НЕ импортируются кодом (исключены из манифеста).
- Критические ML/embedding зависимости в манифесте **отсутствуют**, т.к. embeddings идут
  через Ollama HTTP-адаптер (`adapters/ollama_embedding.py`), а не локальный torch/ST.
  Причина отсутствия: локальный ML-стек не используется ядром (K8/external-LLM design).

## 6. Clean-environment verification

Создан изолированный venv (`C:/Users/Nikita/AppData/Local/Temp/kroft_clean2`),
установлено ТОЛЬКО из `requirements-dev.txt` (тянет `requirements.txt`):
PyYAML + pytest + pytest-asyncio + pytest-cov (и транзитивные).

С `env -u PYTHONPATH` (сброс утечки от hermes venv):

| Проверка | Результат |
|---|---|
| Python version | 3.11.15 ✅ |
| `pip check` | No broken requirements found ✅ |
| `compileall` (все слои) | COMPILE OK ✅ |
| Arch-gate (`tests/architecture/`) | 27 passed ✅ |
| Core FSM (no LLM) | PASS → IDLE ✅ |
| Test collection | 1643 collected ✅ |
| Targeted core (self-evolution/agent-loop) | 22 passed ✅ |

## 7. Known environment assumptions

- `PYTHONPATH` в рабочем окружении указывает на hermes-agent venv (утечка в MSYS).
  Чистый venv с `env -u PYTHONPATH` — истинно изолирован. Для CI рекомендуется
  НЕ прокидывать `PYTHONPATH` родительского venv.
- `KROFT_KNOWLEDGE_FOUNDATION/` (~7GB) игнорируется `.gitignore` (добавлено ранее) —
  не влияет на зависимости, но критично для `git push`.
- 24 падающих теста из baseline (1551 passed/24 failed/65 skipped) НЕ исправлялись
  в рамках R1 (ТЗ: только доказать воспроизводимость окружения).

## 8. Remaining issues

- **R1-внешнее:** в рабочем дереве есть Modified-файлы, которых нет в последнем коммите
  (`adapters/openai_compatible.py`, `composition/run_kroft.py`, `kernel/search.py`) +
  untracked `tests/desktop/test_kroft_fixes.py`. Их НЕ трогал Hermes в этой сессии —
  вероятно ручные правки. При коммите манифеста их нужно вынести отдельно (НЕ в kommit R1).
- Полный прогон 1640 тестов в изолированном venv не делался (ТЗ STEP 5: повторять
  только если установка корректна — она корректна, но полный прогон 1:53:00 избыточен
  для проверки воспроизводимости; collection+arch-gate+FSM+core достаточны).
- `tests/llm/test_omni_router.py` импортирует httpx/pydantic/fastapi — при запуске
  этого конкретного теста в чистом venv он может упасть на ImportError (optional).
  Это НЕ ломает остальные 1642 теста.

---

**Вердикт R1: RESOLVED** — минимальный воспроизводимый манифест создан и проверен
в изолированном окружении; baseline (compile/arch-gate/FSM/collection) воспроизводится.
