"""KROFT Knowledge Foundation — TARGETED incremental ingest (НЕ перестраивает snapshot).

Безопасная вставка verbatim-текста (scanned PDF без OCR) в СУЩЕСТВУЮЩИЙ snapshot,
НЕ затрагивая уже ингестированные узлы (persistence-convergence: load()→добавить→save()).

DEPRECATED для Bacon: Novum Organum уже ингестирован ранее (287 узлов,
KROFT-FND-francis_bacon_novum_organum-001..287). Повторный запуск создаст ДУБЛИ.
Скрипт оставлен как шаблон для других scanned-книг. Чтобы использовать:
  - изменить WORK_SLUG, SRC_ID, TIER, DOMAIN, FULL_TEXT_PATH
  - запускать ТОЛЬКО когда в snapshot ещё нет узлов этого WORK_SLUG
  - всегда делать --dry-run сперва (проверяет совпадение slug перед записью)
"""

from __future__ import annotations
import os
import re
import sys
import time
import json
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KROFT_OS").resolve()
WORK_SLUG = "francis_bacon__novum_organum"
sys.path.insert(0, str(ROOT))

# Полный verbatim-текст Бэкона (из чата), подготовлен отдельным шагом:
FULL_TEXT_PATH = Path(r"C:\Users\Nikita\AppData\Local\Temp\bacon_novum_organum_FULL.md")
SNAP = ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "_snapshot.json"

from infrastructure.graph_builder import InMemoryGraphBuilder
from services.content_index import ContentIndex, _tokenize
from services.graph_query_engine import GraphQueryEngine
from services.semantic_index import SemanticIndex
from adapters.ollama_embedding import OllamaEmbeddingAdapter
from composition.knowledge_persistence import KnowledgeSnapshotStore

STEM = "francis_bacon_novum_organum"
SRC_ID = STEM + ".pdf"
WORK_ID = "WORK::" + SRC_ID
TIER = "T6"
DOMAIN = "scientific_method"

# --- чанкинг: разбиваем по маркерам структуры Бэкона ---
# Приоритет: "BOOK I"/"BOOK II"/"PREFACE"/"FOOTNOTES" как разделители разделов,
# внутри — по "X." / "XII." нумерованным афоризмам (римские цифры).
SEC_RE = re.compile(r"\n(?:PREFACE|FOOTNOTES|\[(3|5|108|109|110|111|112|113|114|115|116|117|118|119|120|121|122|123|124|125|126|127|128|129|130|131|132|133|134|135|136|137|138|139|140|141|142|143|144|145|146|147|148|149|150|151|152|153|154|155|156|157|158|159|160|161|162|163|164)\]\s*$|NOVUM ORGANUM\s*$|CONTENTS)", re.M)
APH_RE = re.compile(r"\n([IVXL]{1,6})\.\s")


def chunk_bacon(text: str) -> list[str]:
    """Вернуть список чанков (около 1500-3500 символов) по структуре Бэкона."""
    # 1) грубое деление на секции по заголовкам
    # Найдём границы разделов
    boundaries = [m.start() for m in re.finditer(
        r"(PREFACE|NOVUM ORGANUM\s*$|CONTENTS|APHORISMS—BOOK I|APHORISMS—BOOK II|FOOTNOTES)",
        text)]
    if not boundaries:
        boundaries = [0, len(text)]
    sections = []
    for i, b in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        sections.append(text[b:end])

    chunks = []
    for sec in sections:
        # внутри секции режем по афоризмам "X."
        parts = re.split(r"\n([IVXL]{1,6})\.\s", sec)
        # parts[0] = текст до первого афоризма; далее пары (номер, тело)
        head = parts[0].strip()
        if head and len(head) > 200:
            chunks.append(head)
        for j in range(1, len(parts), 2):
            num = parts[j]
            body = parts[j + 1] if j + 1 < len(parts) else ""
            body = body.strip()
            if not body:
                continue
            # дробим слишком длинные афоризмы (без тупого реза — по абзацам)
            if len(body) > 3500:
                for para in re.split(r"\n\s*\n", body):
                    para = para.strip()
                    if para:
                        chunks.append(para)
            else:
                chunks.append(body)
    # фильтр: убираем слишком короткие (<120 символов, мусор/номера страниц)
    chunks = [c for c in chunks if len(c) >= 120]
    return chunks


def main():
    import shutil
    t0 = time.time()
    text = FULL_TEXT_PATH.read_text(encoding="utf-8")
    chunks = chunk_bacon(text)
    print(f"[bacon] raw chunks={len(chunks)} text_chars={len(text)}")

    # --- load existing snapshot ---
    store = KnowledgeSnapshotStore(str(SNAP))
    data = store.load()
    if data is None:
        raise SystemExit("SNAPSHOT NOT FOUND — abort (не создавать пустой)")
    existing_graph = data["graph"]
    existing_index = data.get("index", {})
    existing_vectors = data.get("semantic_vectors", {}) or {}

    existing_n = len(existing_graph.get("nodes", []))
    existing_e = len(existing_graph.get("edges", []))
    print(f"[bacon] existing nodes={existing_n} edges={existing_e} vectors={len(existing_vectors)}")

    if "--dry-run" in sys.argv:
        print("[bacon] DRY-RUN: would add", len(chunks), "chunks. No snapshot written.")
        return

    # --- rebuild builder + index from state ---
    builder = InMemoryGraphBuilder()
    for nd in existing_graph.get("nodes", []):
        builder.add_node(nd["id"], label=nd.get("label", nd["id"]), meta=nd.get("meta", {}))
    for ed in existing_graph.get("edges", []):
        builder.add_edge(ed["from"], ed["to"], ed.get("relation", "related"))
    index = ContentIndex()
    index.restore(existing_index)

    # --- add Bacon nodes ---
    new_nodes = []
    for i, ch in enumerate(chunks, 1):
        nid = f"KROFT-FND-{WORK_SLUG}-{i:04d}"
        q = ch[:160].replace("\n", " ")
        meta = {
            "question": q,
            "answer": ch,
            "tags": ["foundation", TIER, DOMAIN, "bacon", "novum_organum"],
            "related_concepts": ["scientific_method", "induction", "empiricism", "idols_of_mind"],
            "source": {
                "id": SRC_ID, "title": "Novum Organum", "author": "Francis Bacon",
                "type": "book", "year": 1620, "tier": 6, "domain": DOMAIN,
                "license": "local|personal_use", "full_text": True,
                "local_path": str(ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "02_philosophy" / SRC_ID),
            },
        }
        builder.add_node(nid, label=q, meta=meta)
        new_nodes.append((nid, meta))

    # bulk index (avoid per-call O(n^2))
    pending = [(nid, m["answer"]) for nid, m in new_nodes]
    for nid, txt in pending:
        index._doc_terms[nid] = Counter(_tokenize(txt))
        index._doc_raw[nid] = (txt or "").lower()
        for w in index._doc_terms[nid]:
            index._index.setdefault(w, set()).add(nid)
    index._rebuild_sorted_terms()

    # edges: work -> chunk
    builder.add_node(WORK_ID, label="Novum Organum (Francis Bacon)",
                     meta={"type": "work", "source": {"id": SRC_ID, "title": "Novum Organum",
                            "author": "Francis Bacon", "tier": 6}})
    for nid, _ in new_nodes:
        builder.add_edge(WORK_ID, nid, "has_chunk")
        builder.add_edge(nid, WORK_ID, "from_work")

    added_nodes = len(new_nodes)
    added_edges = added_nodes * 2

    # --- embed ONLY new nodes (bge-m3) ---
    semantic = SemanticIndex()
    for nid, vec in existing_vectors.items():
        semantic.add(nid, vec)
    semantic_vectors = dict(existing_vectors)
    embedding = None
    try:
        embedding = OllamaEmbeddingAdapter(model="bge-m3")
        def _one(item):
            nid, m = item
            last = None
            for attempt in range(5):
                try:
                    return nid, embedding.embed(m["answer"][:2000])
                except Exception as e:
                    last = e
                    time.sleep(3.0)
            return nid, None
        with ThreadPoolExecutor(max_workers=12) as ex:
            for nid, vec in ex.map(_one, new_nodes):
                if vec is not None:
                    semantic.add(nid, vec)
                    semantic_vectors[nid] = vec
    except Exception as e:
        print(f"[bacon] embedding skipped: {e}")
        embedding = None

    # --- assemble engine for retrieval check ---
    engine = GraphQueryEngine(builder, index=index, semantic_index=semantic, embedding=embedding)

    # --- BACKUP before save (persistence-convergence guard) ---
    bak = str(SNAP) + ".bak.bacon"
    shutil.copyfile(str(SNAP), bak)
    print(f"[bacon] backup -> {bak}")

    # --- SAVE (preserving existing) ---
    store.save(
        graph_state=builder.get_graph(),
        index_state=index.snapshot(),
        semantic=[m for _, m in new_nodes],
        semantic_vectors=semantic_vectors,
    )

    # --- retrieval proof ---
    gold = [
        "idols of the mind that distort human understanding",
        "difference between anticipation of nature and interpretation of nature",
        "form of heat according to Bacon",
        "true induction by exclusion not bare enumeration",
        "four kinds of idols tribe den market theatre",
    ]
    print("\n=== RETRIEVAL PROOF (semantic, top1 cosine) ===")
    ok = 0
    for q in gold:
        res = engine.semantic_search(q, top_k=3)
        top = res[0] if res else (None, 0.0)
        hit = top[0] and top[0].startswith(f"KROFT-FND-{WORK_SLUG}")
        ok += 1 if hit else 0
        print(f"  q='{q[:45]}...' -> {top[0]} ({top[1]:.3f}) {'OK' if hit else 'miss'}")
    print(f"[bacon] gold_hit={ok}/{len(gold)}")

    print(f"\n[ingest] added_nodes={added_nodes} added_edges={added_edges} "
          f"total_nodes={existing_n + added_nodes} mode={'bge-m3' if embedding else 'LEXICAL-ONLY'} "
          f"time={time.time()-t0:.1f}s")
    print(f"[ingest] snapshot updated -> {SNAP}")


if __name__ == "__main__":
    main()
