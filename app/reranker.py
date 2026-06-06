from __future__ import annotations

import math
from dataclasses import replace
from functools import lru_cache

import requests

from app.config import (
    HF_API_KEY,
    RERANK_API_TIMEOUT,
    RERANK_API_URL,
    RERANK_BATCH_SIZE,
    RERANK_ENABLED,
)
from app.schemas import RetrievedChunk


class BGEReranker:
    def __init__(self) -> None:
        self.enabled = RERANK_ENABLED

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        if not chunks:
            return []
        if not self.enabled:
            return chunks[:top_k]
        if not HF_API_KEY:
            raise RuntimeError("HF_API_KEY is required for Hugging Face API reranking")

        scores = []
        for start in range(0, len(chunks), RERANK_BATCH_SIZE):
            batch = chunks[start : start + RERANK_BATCH_SIZE]
            scores.extend(self._api_scores(query, [chunk.text for chunk in batch]))

        ranked = sorted(
            zip(chunks, scores),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            replace(
                chunk,
                score=round(sigmoid(raw_score), 6),
                metadata={**chunk.metadata, "hybrid_score": chunk.score, "rerank_score": raw_score},
            )
            for chunk, raw_score in ranked[:top_k]
        ]

    def _api_scores(self, query: str, documents: list[str]) -> list[float]:
        headers = {"Authorization": f"Bearer {HF_API_KEY}"}
        payload = {
            "inputs": [{"text": query, "text_pair": document} for document in documents],
            "options": {"wait_for_model": True},
        }
        response = requests.post(RERANK_API_URL, headers=headers, json=payload, timeout=RERANK_API_TIMEOUT)
        if response.status_code == 400 and len(documents) > 1:
            return [self._api_scores(query, [document])[0] for document in documents]
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        return self._coerce_scores(payload, expected_count=len(documents))

    def _coerce_scores(self, payload, expected_count: int) -> list[float]:
        if isinstance(payload, dict) and "scores" in payload:
            scores = payload["scores"]
        else:
            scores = payload

        if isinstance(scores, list) and len(scores) == 1 and isinstance(scores[0], list):
            scores = scores[0]

        if not isinstance(scores, list) or len(scores) != expected_count:
            raise RuntimeError(
                f"Unexpected rerank API response shape: expected {expected_count}, "
                f"received {type(scores).__name__}"
            )

        return [self._score_from_item(item) for item in scores]

    def _score_from_item(self, item) -> float:
        if isinstance(item, int | float):
            return float(item)
        if isinstance(item, dict):
            if "score" in item:
                return float(item["score"])
            if "logit" in item:
                return float(item["logit"])
        if isinstance(item, list) and item:
            candidate = max(item, key=lambda value: float(value.get("score", 0.0)) if isinstance(value, dict) else 0.0)
            return self._score_from_item(candidate)
        raise RuntimeError("Unexpected rerank score item from API")


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


@lru_cache(maxsize=1)
def get_reranker() -> BGEReranker:
    return BGEReranker()
