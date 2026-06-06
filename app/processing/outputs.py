from __future__ import annotations

import json

from app.config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, PROCESSED_DIR
from app.schemas import Chunk, RawDocument


def output_scope(value) -> str:
    return (getattr(value, "scope", "") or getattr(value, "ticker", "") or "unknown").lower()


def write_processed_outputs(documents: list[RawDocument], chunks: list[Chunk]) -> None:
    for directory in [PROCESSED_DIR / "text", PROCESSED_DIR / "chunks", PROCESSED_DIR / "metadata"]:
        directory.mkdir(parents=True, exist_ok=True)

    for document in documents:
        out_dir = PROCESSED_DIR / "text" / output_scope(document)
        out_dir.mkdir(parents=True, exist_ok=True)
        name = document.source_path.stem + ".txt"
        (out_dir / name).write_text(document.text, encoding="utf-8")

    chunks_by_scope: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        chunks_by_scope.setdefault(output_scope(chunk), []).append(chunk)

    for scope, scope_chunks in chunks_by_scope.items():
        out_dir = PROCESSED_DIR / "chunks" / scope
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "chunks.jsonl"
        with out_path.open("w", encoding="utf-8") as handle:
            for chunk in scope_chunks:
                handle.write(json.dumps(chunk.__dict__, ensure_ascii=False) + "\n")

    manifest = {
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "tickers": sorted({chunk.ticker for chunk in chunks if chunk.ticker}),
        "scopes": sorted({output_scope(chunk) for chunk in chunks}),
        "chunking": {
            "strategy": "structure-aware-token-based",
            "max_tokens": DEFAULT_CHUNK_SIZE,
            "overlap_tokens": DEFAULT_CHUNK_OVERLAP,
            "structures": ["headings", "tables", "widgets", "paragraphs"],
        },
    }
    (PROCESSED_DIR / "metadata" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def summarize_processed_data(documents: list[RawDocument], chunks: list[Chunk]) -> dict:
    modality_counts: dict[str, int] = {}
    ticker_doc_counts: dict[str, int] = {}
    ticker_chunk_counts: dict[str, int] = {}
    scope_doc_counts: dict[str, int] = {}
    scope_chunk_counts: dict[str, int] = {}
    structure_counts: dict[str, int] = {}

    for document in documents:
        modality_counts[document.modality] = modality_counts.get(document.modality, 0) + 1
        scope = output_scope(document)
        scope_doc_counts[scope] = scope_doc_counts.get(scope, 0) + 1
        if document.ticker:
            ticker_doc_counts[document.ticker] = ticker_doc_counts.get(document.ticker, 0) + 1

    for chunk in chunks:
        scope = output_scope(chunk)
        scope_chunk_counts[scope] = scope_chunk_counts.get(scope, 0) + 1
        if chunk.ticker:
            ticker_chunk_counts[chunk.ticker] = ticker_chunk_counts.get(chunk.ticker, 0) + 1
        structure_counts[chunk.structure_type] = structure_counts.get(chunk.structure_type, 0) + 1

    return {
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "tickers": sorted(ticker_chunk_counts),
        "scopes": sorted(scope_chunk_counts),
        "modalities": dict(sorted(modality_counts.items())),
        "documents_by_ticker": dict(sorted(ticker_doc_counts.items())),
        "chunks_by_ticker": dict(sorted(ticker_chunk_counts.items())),
        "documents_by_scope": dict(sorted(scope_doc_counts.items())),
        "chunks_by_scope": dict(sorted(scope_chunk_counts.items())),
        "structures": dict(sorted(structure_counts.items())),
    }
