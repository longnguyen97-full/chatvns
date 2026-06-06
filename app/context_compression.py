from __future__ import annotations

import re
import unicodedata

from app.config import (
    CONTEXT_COMPRESSION_ENABLED,
    CONTEXT_MAX_CHARS_PER_CHUNK,
    CONTEXT_MAX_SENTENCES_PER_CHUNK,
    CONTEXT_MIN_SENTENCE_CHARS,
)
from app.schemas import RetrievedChunk


FINANCE_TERMS = {
    "doanh",
    "thu",
    "loi",
    "nhuan",
    "lnst",
    "eps",
    "roe",
    "roa",
    "bien",
    "lai",
    "no",
    "vay",
    "tang",
    "giam",
    "gia",
    "muc",
    "tieu",
    "khuyen",
    "nghi",
    "co",
    "phieu",
    "rsi",
    "macd",
    "volume",
    "khoi",
    "luong",
    "thanh",
    "khoan",
}

STOPWORDS = {
    "anh",
    "bao",
    "cho",
    "co",
    "cua",
    "khong",
    "hay",
    "la",
    "mot",
    "nhung",
    "the",
    "thi",
    "trong",
    "va",
    "ve",
    "voi",
}


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_accents).strip()


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w]+", normalize_text(text), flags=re.UNICODE)
        if len(token) > 2 and token not in STOPWORDS
    }


def sentence_candidates(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if not normalized:
        return []
    pieces = re.split(r"(?<=[.!?。！？])\s+|\n+|(?<=;)\s+", normalized)
    return [piece.strip(" -:\t") for piece in pieces if len(piece.strip()) >= CONTEXT_MIN_SENTENCE_CHARS]


def compact_text(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def sentence_score(sentence: str, query_tokens: set[str], ticker: str) -> float:
    sentence_tokens = tokens(sentence)
    if not sentence_tokens:
        return 0.0

    overlap = len(sentence_tokens & query_tokens)
    finance_overlap = len(sentence_tokens & FINANCE_TERMS)
    score = overlap * 2.0 + finance_overlap * 0.35
    if ticker and ticker.lower() in sentence.lower():
        score += 1.0
    if re.search(r"\d", sentence):
        score += 0.5
    return score


def compress_chunk_text(query: str, chunk: RetrievedChunk) -> str:
    if not CONTEXT_COMPRESSION_ENABLED:
        return chunk.text

    sentences = sentence_candidates(chunk.text)
    if not sentences:
        return compact_text(chunk.text, CONTEXT_MAX_CHARS_PER_CHUNK)

    query_tokens = tokens(query)
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: sentence_score(item[1], query_tokens, chunk.ticker),
        reverse=True,
    )
    selected_indexes = sorted(
        index for index, sentence in ranked[:CONTEXT_MAX_SENTENCES_PER_CHUNK] if sentence_score(sentence, query_tokens, chunk.ticker) > 0
    )
    if not selected_indexes:
        return compact_text(chunk.text, CONTEXT_MAX_CHARS_PER_CHUNK)

    compressed = " ".join(sentences[index] for index in selected_indexes)
    return compact_text(compressed, CONTEXT_MAX_CHARS_PER_CHUNK)
