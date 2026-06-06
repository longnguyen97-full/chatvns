from __future__ import annotations

from app.processing.chunking import chunk_documents, chunk_blocks, split_block_by_tokens
from app.processing.documents import iter_raw_documents, modality_from_path, text_dump_exists, ticker_from_path
from app.processing.outputs import summarize_processed_data, write_processed_outputs
from app.processing.readers import load_metadata_for_artifact, read_csv_rows, read_pdf_text, read_raw_file
from app.processing.structures import HTMLStructureParser, parse_document_structures, parse_text_blocks
from app.processing.text_utils import (
    clean_document_text,
    detokenize,
    is_noise_line,
    looks_like_heading,
    looks_like_table,
    looks_like_widget,
    normalize_text,
    rows_to_table_text,
    stable_id,
    token_count,
    tokenize,
)


def process_raw_data():
    documents = iter_raw_documents()
    chunks = chunk_documents(documents)
    write_processed_outputs(documents, chunks)
    return chunks


def process_raw_data_with_summary():
    documents = iter_raw_documents()
    chunks = chunk_documents(documents)
    write_processed_outputs(documents, chunks)
    return chunks, summarize_processed_data(documents, chunks)


__all__ = [
    "HTMLStructureParser",
    "chunk_blocks",
    "chunk_documents",
    "clean_document_text",
    "detokenize",
    "is_noise_line",
    "iter_raw_documents",
    "load_metadata_for_artifact",
    "looks_like_heading",
    "looks_like_table",
    "looks_like_widget",
    "modality_from_path",
    "normalize_text",
    "parse_document_structures",
    "parse_text_blocks",
    "process_raw_data",
    "process_raw_data_with_summary",
    "read_csv_rows",
    "read_pdf_text",
    "read_raw_file",
    "rows_to_table_text",
    "split_block_by_tokens",
    "stable_id",
    "summarize_processed_data",
    "text_dump_exists",
    "ticker_from_path",
    "token_count",
    "tokenize",
    "write_processed_outputs",
]
