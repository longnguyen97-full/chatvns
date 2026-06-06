from __future__ import annotations

from app.config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, RAW_DIR
from app.processing.readers import read_csv_rows
from app.processing.structures import parse_document_structures
from app.processing.text_utils import detokenize, stable_id, token_count, tokenize
from app.schemas import Chunk, RawDocument, StructureBlock


def split_block_by_tokens(block: StructureBlock, max_tokens: int, overlap: int) -> list[StructureBlock]:
    tokens = tokenize(block.text)
    if len(tokens) <= max_tokens:
        return [block]

    blocks: list[StructureBlock] = []
    start = 0
    part_index = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        text = detokenize(tokens[start:end])
        blocks.append(
            StructureBlock(
                text=text,
                structure_type=block.structure_type,
                heading_path=block.heading_path,
                metadata={**block.metadata, "split_part": part_index},
            )
        )
        if end >= len(tokens):
            break
        start = max(end - overlap, start + 1)
        part_index += 1
    return blocks


def chunk_blocks(
    blocks: list[StructureBlock],
    max_tokens: int,
    overlap: int,
) -> list[tuple[str, str, list[str], int, dict]]:
    chunks: list[tuple[str, str, list[str], int, dict]] = []
    current_blocks: list[StructureBlock] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_blocks, current_tokens
        if not current_blocks:
            return
        text = "\n\n".join(block.text for block in current_blocks)
        structure_types = [block.structure_type for block in current_blocks]
        heading_path = current_blocks[-1].heading_path
        metadata = {
            "structure_types": structure_types,
            "primary_structure_type": structure_types[0],
            "block_count": len(current_blocks),
            "block_metadata": [block.metadata for block in current_blocks],
        }
        chunks.append((text, structure_types[0], heading_path, token_count(text), metadata))
        current_blocks = []
        current_tokens = 0

    for block in blocks:
        for part in split_block_by_tokens(block, max_tokens, overlap):
            part_tokens = token_count(part.text)
            if current_blocks and current_tokens + part_tokens > max_tokens:
                flush()
            current_blocks.append(part)
            current_tokens += part_tokens

    flush()
    return chunks


def enrich_chunk_metadata(document: RawDocument, block_metadata: dict) -> dict:
    return {
        **document.metadata,
        "document_id": document.id,
        "source_file": document.source_path.name,
        "parser": "structure-aware-token-chunker",
        **block_metadata,
    }


def chunk_documents(
    documents: list[RawDocument],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        source_path = document.source_path.relative_to(RAW_DIR.parent).as_posix()
        csv_rows = read_csv_rows(document.source_path) if document.source_path.suffix.lower() == ".csv" else None
        blocks = parse_document_structures(document, csv_rows=csv_rows)
        for index, (text, structure_type, heading_path, tokens, block_metadata) in enumerate(
            chunk_blocks(blocks, chunk_size, overlap)
        ):
            chunks.append(
                Chunk(
                    id=stable_id(document.id, str(index), text[:120]),
                    text=text,
                    ticker=document.ticker,
                    modality=document.modality,
                    source_path=source_path,
                    chunk_index=index,
                    structure_type=structure_type,
                    heading_path=heading_path,
                    token_count=tokens,
                    metadata=enrich_chunk_metadata(document, block_metadata),
                    scope=document.scope,
                )
            )
    return chunks
