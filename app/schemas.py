from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RawDocument:
    id: str
    text: str
    source_path: Path
    modality: str
    ticker: str
    metadata: dict
    scope: str = ""


@dataclass(frozen=True)
class StructureBlock:
    text: str
    structure_type: str
    heading_path: list[str]
    metadata: dict


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    ticker: str
    modality: str
    source_path: str
    chunk_index: int
    structure_type: str
    heading_path: list[str]
    token_count: int
    metadata: dict
    scope: str = ""


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    score: float
    ticker: str
    modality: str
    source_path: str
    structure_type: str
    heading_path: list[str]
    metadata: dict
    scope: str = ""
