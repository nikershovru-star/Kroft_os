"""LLMEntityExtractor — Knowledge Platform extraction adapter (Wave 8, ADR-011 Phase C).

Uses the Router (Wave 6) to ask an LLM for entities and relation HYPOTHESES.
The router is injected as a structural port
`Callable[[ModelQuery], LlmResponse]` — this adapter never imports the concrete
Router class, so the dependency axis stays `adapters -> contracts` (LAW 2).

Contract with the model (ADR-011 §2.2):
    the LLM output is a HYPOTHESIS, never a fact. Validation happens later.

Parsing is defensive: models wrap JSON in prose or ```json fences, and stdlib
`json` is the only parser allowed (LAW: stdlib-first — no langchain/tiktoken).
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from contracts.i_knowledge import Entity, Hypothesis, IEntityExtractor
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_policy import PolicyContext

RouterFn = Callable[[ModelQuery], LlmResponse]

ENTITY_PROMPT = (
    "Извлеки сущности и связи из текста в формате JSON: "
    '[{"subject": "...", "predicate": "...", "object": "..."}]. '
    "Отвечай ТОЛЬКО валидным JSON-массивом, без пояснений.\n\nТекст:\n{text}"
)

#: placeholder substituted into the prompt template. `str.format` is NOT used:
#: the template itself contains JSON braces, and format() would raise
#: KeyError('"subject"') on them. Plain replace is brace-safe.
TEXT_PLACEHOLDER = "{text}"

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json_array(raw: str) -> List[Dict[str, Any]]:
    """Best-effort JSON-array recovery from a model answer (stdlib only).

    Handles: bare array, ```json fenced array, array embedded in prose.
    Returns [] on anything unparseable — extraction failure is not an exception,
    it is simply zero hypotheses (the pipeline stays observable, LAW 5).
    """
    if not raw:
        return []
    text = raw.strip()

    candidates: List[str] = [text]
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            # tolerate {"relations": [...]} / {"entities": [...]}
            for key in ("relations", "entities", "items", "data"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            else:
                data = [data]
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    return []


class LLMEntityExtractor(IEntityExtractor):
    """Extracts entities / relation hypotheses from text through the Router.

    The router picks a model via the PolicyEngine; we only declare what the
    query needs (`reasoning=True`, `json_mode=True`, task="entity_extraction"),
    matching TaskCategory.ENTITY_EXTRACTION from the Evaluation Platform.
    """

    def __init__(
        self,
        router: RouterFn,
        prompt_template: str = ENTITY_PROMPT,
        task: str = "entity_extraction",
    ) -> None:
        self._router = router
        self._prompt_template = prompt_template
        self._task = task
        self.last_response: Optional[LlmResponse] = None

    # --- internals ---------------------------------------------------------
    def _build_prompt(self, text: str) -> str:
        tmpl = self._prompt_template
        if TEXT_PLACEHOLDER in tmpl:
            return tmpl.replace(TEXT_PLACEHOLDER, text)
        return f"{tmpl}\n\n{text}"

    def _ask(self, text: str) -> LlmResponse:
        query = ModelQuery(
            task=self._task,
            reasoning=True,       # extraction needs a reasoning-capable model
            json_mode=True,
            prompt=self._build_prompt(text),
        )
        resp = self._router(query)
        self.last_response = resp
        return resp

    @staticmethod
    def _source_of(resp: LlmResponse) -> str:
        return resp.actual_model or resp.model or resp.provider or "unknown"

    # --- IEntityExtractor --------------------------------------------------
    def extract(self, text: str, context: PolicyContext) -> List[Entity]:
        """Entities are derived from the subject/object slots of the triples.

        v0.1 keeps one LLM round-trip per chunk: asking twice (once for
        entities, once for relations) would double cost for the same
        information (LAW 5: measure before you spend).
        """
        resp = self._ask(text)
        if not resp.ok():
            return []
        source = self._source_of(resp)
        seen: Dict[str, Entity] = {}
        for item in _extract_json_array(resp.text):
            for slot in ("subject", "object"):
                name = str(item.get(slot, "") or "").strip()
                if not name or name in seen:
                    continue
                seen[name] = Entity(
                    name=name,
                    type="concept",
                    evidence=text,
                    source=source,
                )
        return list(seen.values())

    def extract_relations(self, text: str, context: PolicyContext) -> List[Hypothesis]:
        resp = self._ask(text)
        if not resp.ok():
            return []
        source = self._source_of(resp)
        evidence = resp.trace_id or text
        out: List[Hypothesis] = []
        for item in _extract_json_array(resp.text):
            h = Hypothesis(
                subject=str(item.get("subject", "") or "").strip(),
                predicate=str(item.get("predicate", "") or "").strip(),
                object=str(item.get("object", "") or "").strip(),
                source=source,
                evidence=evidence,
                confidence=0.0,   # unknown until Evaluation scores it
            )
            if h.is_well_formed():
                out.append(h)
        return out
