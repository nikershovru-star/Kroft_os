---
tags: [kroft, keh, audit, dataviz-template, methodology]
created: 2026-08-13
author: Hermes
status: v1.0
parent: KEH
summary: "Reusable dataviz template for KROFT_OS staged audit reports. Renders BEFORE/AFTER, Recall@5/10, MRR, STATUS lines as a neo-brutalist console infographic (uses baoyu-infographic / architecture-diagram skills)."
---

# KROFT_OS Audit Report — Dataviz Template

Every staged audit (L6/L7/L8/L9, persistence, crypto, repr-gate) ends with a RIGID report.
This template turns that text report into a visual artifact so metrics are legible at a glance.
Render via `baoyu-infographic` (or `architecture-diagram`) skill — neo-brutalist "console"
style (hard shadow, monospace/Space Mono, Unbounded headings).

## 1. Mandatory text skeleton (paste into the audit, ALWAYS)
```
## EXECUTION REPORT — <PHASE>
BEFORE: nodes=<N> vectors=<V> edges=<E>
AFTER:  nodes=<N'> vectors=<V'> edges=<E'>
Recall@5=<r5>  Recall@10=<r10>  MRR=<mrr>
cross-domain=<PASS|PARTIAL|FAIL>
incremental=<PASS|PARTIAL|FAIL>
L<N> STATUS: PASS | PARTIAL | BROKEN
PRODUCTION: UNCHANGED | CHANGED
PATCH: NONE | <files>
NEXT BOTTLENECK: <text>
```

## 2. Visual blocks (one card per metric)
| Block | Content | Color cue |
|---|---|---|
| BEFORE→AFTER | delta bars (nodes/vectors/edges) | green if ↑, red if ↓ unexpected |
| Retrieval | Recall@5 / @10 / MRR as 3 gauges | amber if below threshold |
| Gate matrix | L# STATUS grid (PASS/ PARTIAL/ BROKEN) | green / amber / red |
| Production | UNCHANGED vs CHANGED banner | grey vs blue |
| Bottleneck | single-line callout | hard-shadow box |

## 3. Render command (Hermes)
After writing the text skeleton in the audit note, emit the infographic:
- Use `baoyu-infographic` skill with layout="report", style="neo-brutalist-console".
- Feed the skeleton above as the data source.
- Output as standalone HTML in `docs/architecture/KEH/audits/<phase>-report.html`
  (and link from the audit note).

## 4. Why this matters (L9 Benchmark Lab)
Staged audits accumulate. Visual history lets the Architect compare recall/MRR trends
across waves without re-reading 12 markdown tables — directly feeds the L9 A/B benchmark
loop and the L3 org-memory (ADR-E) of "what each wave actually changed".

## 5. LAW/K8 note
Template lives in `docs/` (AKB-adjacent), NOT in runtime/ — satisfies LAW K8.
It is a reporting convention, not executable code.
