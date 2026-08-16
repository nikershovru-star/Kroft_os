"""Simple ensemble orchestrator — parallel multi-model call + best-confidence merge (ТЗ-ECHO, E4).

K1/K6: stdlib (asyncio + concurrent.futures) + contracts only. Reuses ``ILlm`` for each
candidate; network I/O stays inside each client (IHttpTransport). Fan-out is parallel via
a thread pool (ILlm.complete is blocking/sync), wall latency = max, not sum.

Merge strategy (E4 default = BEST_CONFIDENCE): pick the non-failed response with the
highest proxy confidence. Proxy = non-empty text length weighted by token count; this is
a cheap, deterministic heuristic (no extra model call). E5 adds RRF_TEXT later.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

from contracts.i_ensemble_orchestrator import (
    EnsembleResult,
    IEnsembleOrchestrator,
    MergeStrategy,
)
from contracts.i_llm import ILlm, LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout


def _proxy_confidence(resp: LlmResponse) -> float:
    """Cheap confidence proxy: longer, token-richer non-error answers score higher."""
    if resp is None or resp.error is not None or not resp.text.strip():
        return 0.0
    # length + token signal, capped to avoid runaway scaling
    return min(1.0, (len(resp.text) / 2000.0) * 0.6 + (resp.tokens_out / 500.0) * 0.4)


class SimpleEnsembleOrchestrator(IEnsembleOrchestrator):
    """Fan out ``query`` over ``clients`` in parallel; merge by strategy."""

    def __init__(self, max_workers: int = 3) -> None:
        # Cap concurrency: a 2-model ensemble must stay within the +20% latency budget.
        self._max_workers = max(1, min(max_workers, 8))

    def run(
        self,
        query: ModelQuery,
        clients: List[ILlm],
        strategy: MergeStrategy = MergeStrategy.BEST_CONFIDENCE,
    ) -> EnsembleResult:
        usable = [c for c in clients if c is not None]
        if not usable:
            return EnsembleResult(
                response=LlmResponse(text="", error="ensemble: no clients provided"),
                strategy=strategy,
            )

        # Single client: delegate directly (no thread overhead, no merge).
        if len(usable) == 1:
            t0 = time.perf_counter()
            try:
                resp = usable[0].complete(query)
            except (LLMError, LLMTimeout) as exc:
                resp = LlmResponse(text="", error=f"ensemble single failed: {exc}")
            wall = (time.perf_counter() - t0) * 1000.0
            return EnsembleResult(
                response=resp,
                per_model={getattr(usable[0], "provider", "model"): resp},
                strategy=strategy,
                latency_ms=wall,
                cost=resp.cost,
            )

        # Parallel fan-out (blocking clients -> threads). Results are collected in the
        # MAIN thread via future.result() (G7: no shared-dict mutation from workers; the
        # GIL does not make incidental dict writes a contract). Worker exceptions are
        # captured per-future so one rogue client can't kill the merge.
        from concurrent.futures import Future
        per_model: dict[str, LlmResponse] = {}
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(usable))) as ex:
            futures: List[tuple[str, Future]] = []
            for client in usable:
                name = getattr(client, "provider", "model")
                fut = ex.submit(self._safe_call, client, query)
                futures.append((name, fut))
            for name, fut in futures:
                try:
                    resp = fut.result()
                except Exception as exc:  # defensive: never let a future explosion escape
                    resp = LlmResponse(text="", error=f"{name} error: {exc}")
                # G8: dedupe provider names so a duplicate doesn't clobber a result.
                key = name
                if key in per_model:
                    key = f"{name}#{len(per_model)}"
                per_model[key] = resp
        wall = (time.perf_counter() - t0) * 1000.0

        if strategy is MergeStrategy.RRF_TEXT:
            merged = self._merge_rrf(per_model)
        else:
            merged = self._merge_best_confidence(per_model)

        # Cost semantics (STEP 12): total = sum of attempted calls (cost-aware router).
        # Successful and failed (cost 0) both counted; this is the spend the router caused.
        total_cost = sum(r.cost for r in per_model.values())
        return EnsembleResult(
            response=merged,
            per_model=per_model,
            strategy=strategy,
            latency_ms=wall,
            cost=total_cost,
        )

    @staticmethod
    def _safe_call(client: ILlm, query: ModelQuery) -> LlmResponse:
        name = getattr(client, "provider", "model")
        try:
            return client.complete(query)
        except (LLMError, LLMTimeout) as exc:
            return LlmResponse(text="", error=f"{name} failed: {exc}")
        except Exception as exc:  # defensive: a rogue adapter must not kill the merge
            return LlmResponse(text="", error=f"{name} error: {exc}")

    @staticmethod
    def _merge_best_confidence(per_model: dict[str, LlmResponse]) -> LlmResponse:
        ok = [r for r in per_model.values() if r.error is None and r.text.strip()]
        if not ok:
            first_err = next(iter(per_model.values()))
            return LlmResponse(text="", error=f"ensemble: all failed ({first_err.error})")
        best = max(ok, key=_proxy_confidence)
        # annotate which model won (observability)
        winner = [n for n, r in per_model.items() if r is best]
        best = LlmResponse(
            text=best.text,
            provider=best.provider,
            model=best.model,
            actual_provider=best.actual_provider or (winner[0] if winner else ""),
            actual_model=best.actual_model,
            trace_id=best.trace_id,
            tokens=best.tokens,
            tokens_in=best.tokens_in,
            tokens_out=best.tokens_out,
            latency_ms=best.latency_ms,
            cost=best.cost,
            error=None,
        )
        return best

    @staticmethod
    def _merge_rrf(per_model: dict[str, LlmResponse]) -> LlmResponse:
        """Placeholder RRF-text merge (E5 will flesh this out).

        For E1 we fall back to best-confidence so the strategy enum is wired end-to-end
        without a half-built algorithm. Marked clearly so E5 replaces the body.
        """
        return SimpleEnsembleOrchestrator._merge_best_confidence(per_model)
