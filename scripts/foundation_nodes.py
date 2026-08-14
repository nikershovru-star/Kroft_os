"""KROFT Knowledge Foundation — chunk sidecars -> KROFT-FND-*.md nodes (INGESTION v1.0, Этап D).

Reuses extracted sidecars from scripts/foundation_extract.py. Generates Knowledge
Nodes in the EXACT format read_node_file() expects (ТЗ §7):
  ---
  id: KROFT-FND-<tier>-<seq>
  question: <real content of chunk>
  answer: <extracted text>
  tags: [foundation, <tier>, <domain>]
  related_concepts: [...]
  source: {id,title,author,year,edition,type,domain,tier,source_url,license,language,local_path,page_start,page_end}
  ---
No fabricated knowledge: question is derived from the chunk's first sentence/heading;
answer is the verbatim extracted text. Provenance (source + page bounds) mandatory.

Output: KROFT_KNOWLEDGE_FOUNDATION/_nodes/KROFT-FND-*.md
"""
from __future__ import annotations

import json
import re
import sys
import yaml
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parent.parent / "KROFT_KNOWLEDGE_FOUNDATION"
EXTRACTED = FOUNDATION / "_extracted"
NODES_DIR = FOUNDATION / "_nodes"
NODES_DIR.mkdir(exist_ok=True)

# Map folder -> (tier, domain) for tagging (ТЗ §10 minimal tags)
FOLDER_META = {
    "01_logic": ("T6", "scientific_method"),
    "02_philosophy": ("T6", "scientific_method"),
    "03_mathematics": ("T2", "reasoning"),
    "04_information_theory": ("T1", "information_theory"),
    "05_ai": ("T2", "ai"),
    "06_cognition": ("T1", "cognition"),
    "07_computer_science": ("T1", "operating_systems"),
    "08_software_architecture": ("T1", "software_architecture"),
    "09_distributed_systems": ("T4", "distributed_systems"),
    "12_control_systems": ("T1", "cybernetics"),
}

# filename -> title/author metadata (from audit, ТЗ §15; unknown where unknown)
META = {
    "aristotle_organon": ("Organon", "Aristotle", "unknown", "book", "philosophy", "T6"),
    "aristotle_metaphysics": ("Metaphysics", "Aristotle", "unknown", "book", "philosophy", "T6"),
    "bertrand_russell_the_problems_of_philosophy": ("The Problems of Philosophy", "B. Russell", "1912", "book", "philosophy", "T6"),
    "david_hume_an_enquiry_concerning_human_understanding": ("An Enquiry Concerning Human Understanding", "D. Hume", "unknown", "book", "philosophy", "T6"),
    "francis_bacon_novum_organum": ("Novum Organum", "F. Bacon", "1620", "book", "scientific_method", "T6"),
    "immanuel_kant_critique_of_pure_reason": ("Critique of Pure Reason", "I. Kant", "unknown", "book", "philosophy", "T6"),
    "plato_the_republic": ("The Republic", "Plato", "unknown", "book", "philosophy", "T6"),
    "rene_descartes_discourse_on_the_method": ("Discourse on the Method", "R. Descartes", "1637", "book", "scientific_method", "T6"),
    "courant___robbins_what_is_mathematics": ("What is Mathematics", "Courant & Robbins", "unknown", "book", "mathematics", "T2"),
    "george_polya_how_to_solve_it": ("How to Solve It", "G. Polya", "unknown", "book", "reasoning", "T2"),
    "john_von_neumann_the_computer_and_the_brain": ("The Computer and the Brain", "J. von Neumann", "unknown", "book", "cognition", "T2"),
    "claude_shannon_a_mathematical_theory_of_communication": ("A Mathematical Theory of Communication", "C. E. Shannon", "1948", "paper", "information_theory", "T1"),
    "christopher_bishop_pattern_recognition_and_machine_learning": ("Pattern Recognition and Machine Learning", "C. Bishop", "unknown", "book", "ai", "T2"),
    "ian_goodfellow__yoshua_bengio__aaron_courville_deep_learning": ("Deep Learning", "Goodfellow et al.", "unknown", "book", "ai", "T2"),
    "kevin_murphy_probabilistic_machine_learning__an_introduction": ("Probabilistic Machine Learning", "K. Murphy", "unknown", "book", "ai", "T2"),
    "richard_s__sutton__andrew_g__barto_reinforcement_learning__an_introduction__2ed_": ("Reinforcement Learning: An Introduction", "Sutton & Barto", "2017", "book", "ai", "T2"),
    "allen_newell__herbert_a__simon_human_problem_solving": ("Human Problem Solving", "Newell & Simon", "1971", "paper", "cognition", "T1"),
    "herbert_a__simon_the_sciences_of_the_artificial__3rd_ed": ("The Sciences of the Artificial", "H. A. Simon", "1996", "book", "cognition", "T1"),
    "andrew_tanenbaum_computer_networks": ("Computer Networks", "Tanenbaum", "unknown", "book", "operating_systems", "T1"),
    "bryant___o_hallaron_computer_systems__a_programmer_s_perspective": ("Computer Systems: A Programmer's Perspective", "Bryant & O'Hallaron", "unknown", "book", "operating_systems", "T1"),
    "james_kurose__keith_ross_computer_networking__a_top-down_approach": ("Computer Networking: A Top-Down Approach", "Kurose & Ross", "unknown", "book", "operating_systems", "T1"),
    "eric_evans_domain-driven_design": ("Domain-Driven Design", "E. Evans", "2003", "book", "software_architecture", "T1"),
    "martin_kleppmann_designing_data-intensive_applications": ("Designing Data-Intensive Applications", "M. Kleppmann", "unknown", "book", "software_architecture", "T1"),
    "jeffrey_dean__sanjay_ghemawat_mapreduce": ("MapReduce", "Dean & Ghemawat", "2004", "paper", "distributed_systems", "T4"),
    "leslie_lamport_the_part-time_parliament__paxos": ("The Part-Time Parliament (Paxos Made Simple)", "L. Lamport", "2001", "paper", "distributed_systems", "T4"),
    "leslie_lamport_time__clocks__and_the_ordering_of_events_in_a_distributed_system": ("Time, Clocks, and the Ordering of Events in a Distributed System", "L. Lamport", "1978", "paper", "distributed_systems", "T4"),
    "karl_astrom__richard_murray_feedback_systems": ("Feedback Systems", "Åström & Murray", "unknown", "book", "cybernetics", "T1"),
    "norbert_wiener_cybernetics__control_and_communication_in_the_animal_and_the_mach": ("Cybernetics (fragment/archival)", "N. Wiener", "1949", "paper", "cybernetics", "T1"),
    "norbert_wiener_the_human_use_of_human_beings": ("The Human Use of Human Beings", "N. Wiener", "unknown", "book", "cybernetics", "T1"),
}

_LICENSE = {
    "paper": "open (author/preprint)",
    "book": "purchase/library (NOT_LEGALLY_AVAILABLE full)",
}


def _make_question(text: str) -> str:
    """Derive a real question/summary from chunk content (no fabrication)."""
    # first heading-like line or first sentence
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        first = lines[0]
        if len(first) > 120:
            first = first[:117] + "..."
        return first
    return text[:120]


def generate_for(sidecar_path: Path) -> list[str]:
    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    meta = data["meta"]
    stem = sidecar_path.stem
    title, author, year, typ, domain, tier = META.get(
        stem, ("unknown", "unknown", "unknown", "unknown", "unknown", "unknown"))
    folder = sidecar_path.parent.parent  # _extracted's parent = FOUNDATION
    # derive tier/domain from folder if unknown
    rel = sidecar_path.relative_to(FOUNDATION).parts
    fmeta = FOLDER_META.get(rel[0], (tier, domain))
    tier = fmeta[0] if tier == "unknown" else tier
    domain = fmeta[1] if domain == "unknown" else domain

    written = []
    seq = 0
    for ch in data.get("chunks", []):
        seq += 1
        nid = f"KROFT-FND-{tier}-{stem[:24]}-{seq:03d}"
        q = _make_question(ch["text"])
        tags = ["foundation", tier, domain]
        lic = _LICENSE.get(typ, "unknown")
        source = {
            "id": stem + ".pdf",
            "title": title,
            "author": author,
            "year": year,
            "type": typ,
            "domain": domain,
            "tier": tier,
            "source_url": "local://KROFT_KNOWLEDGE_FOUNDATION/" + meta["path"],
            "license": lic,
            "language": "en",
            "local_path": meta["path"],
            "page_start": ch["page_start"],
            "page_end": ch["page_end"],
        }
        fm = {
            "id": nid,
            "question": q,
            "answer": ch["text"],
            "tags": tags,
            "related_concepts": [],
            "source": source,
        }
        # yaml-ish manual dump (avoid yaml import quirks with multiline)
        body = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + ch["text"]
        out = NODES_DIR / (nid + ".md")
        out.write_text(body, encoding="utf-8")
        written.append(str(out))
    return written


def main() -> int:
    sidecars = sorted(EXTRACTED.glob("*.json"))
    total = 0
    for sc in sidecars:
        total += len(generate_for(sc))
    print(f"Generated {total} KROFT-FND nodes into {NODES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
