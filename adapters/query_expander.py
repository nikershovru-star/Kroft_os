"""RU/EN query rewrite/expansion for paraphrase-robust retrieval (ADR-0XX, P0-B).

K6-compliant: adapters/ imports ONLY contracts.* + stdlib. No model, no network —
pure lexical normalization + synonym expansion over a small bilingual tech lexicon.
Wraps retrieval so a paraphrased query (e.g. "как настроить" vs "конфигурация
инструкция") expands toward the canonical node vocabulary, lifting token-overlap /
cosine against stored nodes.

Deterministic (I-09): same input -> same expansion. Safe to unit-test without Ollama.
"""
from __future__ import annotations

import re
from typing import Dict, List

# Minimal RU/EN tech synonym map. Key = canonical token, values = paraphrases that
# should expand/replace toward it. Grows from the KROFT_KNOWLEDGE vocabulary over time.
# NOTE: настройка/конфигурация are merged into one canonical group ("конфигурация")
# because in the KROFT corpus they denote the same concept.
_SYNONYMS: Dict[str, List[str]] = {
    "конфигурация": ["настройка", "конфиг", "настроить", "установка", "setup",
                     "сконфигурировать", "отрегулировать"],
    "инструкция": ["руководство", "гайд", "мануал", "howto", "руководство"],
    "ошибка": ["error", "баг", "сбой", "исключение", "exception"],
    "запуск": ["старт", "run", "выполнение", "execute", "запустить"],
    "остановка": ["стоп", "stop", "завершение", "shutdown"],
    "память": ["memory", "хранилище", "store", "запоминание"],
    "граф": ["graph", "сеть", "узлы", "network"],
    "агент": ["agent", "бот", "исполнитель", "executor", "бота", "агента"],
    "модель": ["model", "llm", "нейросеть", "network"],
    "поиск": ["search", "retrieval", "найти", "выборка"],
    "эволюция": ["evolution", "развитие", "самообучение", "self-evolution"],
}

_STOPWORDS = {
    "как", "для", "чего", "это", "the", "a", "an", "of", "to", "in", "is",
    "и", "с", "по", "на", "в", "что", "где", "когда", "зачем", "чтобы",
}

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")


class QueryExpander:
    """Deterministic RU/EN query rewriter: normalize + synonym-expand + lemmatize-lite."""

    def __init__(self, synonyms: Dict[str, List[str]] | None = None,
                 stopwords: set | None = None) -> None:
        self._syn = synonyms or _SYNONYMS
        self._stop = stopwords or _STOPWORDS
        # reverse index: paraphrase -> canonical
        self._to_canonical: Dict[str, str] = {}
        for canon, alts in self._syn.items():
            self._to_canonical[canon] = canon
            for a in alts:
                self._to_canonical[a] = canon

    def expand(self, query: str, max_tokens: int = 12) -> str:
        """Return a rewritten query: each token replaced by its canonical form.

        Paraphrase tokens ("настроить", "бот") become canonical vocabulary
        ("конфигурация", "агент") present in indexed nodes, lifting token-overlap
        and cosine against stored content. Stopwords are dropped. Deterministic.
        """
        if not query or not query.strip():
            return ""
        toks = _TOKEN_RE.findall(query.lower())
        out: List[str] = []
        for t in toks:
            if t in self._stop:
                continue
            canon = self._to_canonical.get(t)
            # replace with canonical if known, else keep the original token
            out.append(canon if canon else t)
        # dedupe preserving order, cap length
        seen = set()
        deduped: List[str] = []
        for t in out:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        return " ".join(deduped[:max_tokens])

    def expand_tokens(self, query: str) -> List[str]:
        return self.expand(query).split()
