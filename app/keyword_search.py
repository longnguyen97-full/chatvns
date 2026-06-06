from __future__ import annotations

import json
import math
import re

from app.config import PROCESSED_DIR
from app.schemas import RetrievedChunk


TOKEN_PATTERN = re.compile(r"[\wÀ-ỹ]+", flags=re.UNICODE)


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def load_processed_chunks(ticker: str | None = None) -> list[dict]:
    chunk_root = PROCESSED_DIR / "chunks"
    if not chunk_root.exists():
        return []

    paths = []
    if ticker:
        paths = [chunk_root / ticker.upper() / "chunks.jsonl"]
    else:
        paths = list(chunk_root.glob("*/chunks.jsonl"))
        if (chunk_root / "market" / "chunks.jsonl").exists():
            paths = [path for path in paths if path.parent.name != "MARKET"]

    chunks: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return chunks


def fallback_bm25_scores(query_tokens: list[str], corpus_tokens: list[list[str]]) -> list[float]:
    if not corpus_tokens:
        return []

    doc_count = len(corpus_tokens)
    doc_freq: dict[str, int] = {}
    for tokens in corpus_tokens:
        for token in set(tokens):
            doc_freq[token] = doc_freq.get(token, 0) + 1

    scores: list[float] = []
    for tokens in corpus_tokens:
        token_count = len(tokens) or 1
        term_freq: dict[str, int] = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1

        score = 0.0
        for token in query_tokens:
            if token not in term_freq:
                continue
            idf = math.log((doc_count - doc_freq.get(token, 0) + 0.5) / (doc_freq.get(token, 0) + 0.5) + 1)
            score += idf * (term_freq[token] / token_count)
        scores.append(score)
    return scores


def bm25_scores(query: str, chunks: list[dict]) -> list[float]:
    query_tokens = tokenize(query)
    corpus_tokens = [tokenize(str(chunk.get("text", ""))) for chunk in chunks]
    if not query_tokens or not corpus_tokens:
        return [0.0] * len(chunks)

    try:
        from rank_bm25 import BM25Okapi

        bm25 = BM25Okapi(corpus_tokens)
        return [float(score) for score in bm25.get_scores(query_tokens)]
    except Exception:
        return fallback_bm25_scores(query_tokens, corpus_tokens)


def normalize_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    min_score = min(scores)
    max_score = max(scores)
    if max_score == min_score:
        return [0.0 if max_score == 0 else 1.0 for _ in scores]
    return [(score - min_score) / (max_score - min_score) for score in scores]


def chunk_to_retrieved(chunk: dict, score: float) -> RetrievedChunk:
    source_path = str(chunk.get("source_path", ""))
    metadata = dict(chunk.get("metadata") or {})
    raw_ticker = str(chunk.get("ticker", ""))
    scope = str(chunk.get("scope") or metadata.get("scope") or raw_ticker or "")
    if raw_ticker.upper() == "MARKET" or "world_market" in source_path or "/market/" in source_path.replace("\\", "/"):
        raw_ticker = ""
        scope = "market"
    return RetrievedChunk(
        id=str(chunk.get("id", "")),
        text=str(chunk.get("text", "")),
        score=score,
        ticker=raw_ticker,
        modality=str(chunk.get("modality", "")),
        source_path=source_path,
        structure_type=str(chunk.get("structure_type", "")),
        heading_path=list(chunk.get("heading_path") or []),
        metadata=metadata,
        scope=scope,
    )


def keyword_search(query: str, top_k: int, ticker: str | None = None) -> list[RetrievedChunk]:
    chunks = load_processed_chunks(ticker=ticker)
    scores = normalize_scores(bm25_scores(query, chunks))
    ranked = sorted(
        zip(chunks, scores),
        key=lambda item: item[1],
        reverse=True,
    )
    return [
        chunk_to_retrieved(chunk, score)
        for chunk, score in ranked[:top_k]
        if score > 0
    ]
