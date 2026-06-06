from __future__ import annotations

from dataclasses import replace

from app.config import RERANK_CANDIDATE_LIMIT
from app.keyword_search import keyword_search
from app.reranker import get_reranker
from app.schemas import RetrievedChunk
from app.vector_store import retrieve as dense_retrieve


def hybrid_retrieve(
    query: str,
    top_k: int,
    ticker: str | None = None,
    dense_weight: float = 0.65,
    keyword_weight: float = 0.35,
    rrf_k: int = 60,
) -> list[RetrievedChunk]:
    dense_limit = max(top_k * 4, 20)
    keyword_limit = max(top_k * 4, 20)

    dense_hits = dense_retrieve(query, top_k=dense_limit, ticker=ticker)
    keyword_hits = keyword_search(query, top_k=keyword_limit, ticker=ticker)

    merged: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}

    for rank, hit in enumerate(dense_hits, start=1):
        merged[hit.id] = hit
        scores[hit.id] = scores.get(hit.id, 0.0) + dense_weight / (rrf_k + rank)

    for rank, hit in enumerate(keyword_hits, start=1):
        merged.setdefault(hit.id, hit)
        scores[hit.id] = scores.get(hit.id, 0.0) + keyword_weight / (rrf_k + rank)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    candidate_limit = max(top_k, RERANK_CANDIDATE_LIMIT)
    candidates = [
        replace(merged[chunk_id], score=score)
        for chunk_id, score in ranked[:candidate_limit]
    ]
    return get_reranker().rerank(query, candidates, top_k=top_k)
