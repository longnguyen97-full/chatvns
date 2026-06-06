from __future__ import annotations

from pathlib import Path

from app.config import RAW_DIR
from app.processing.constants import IMAGE_EXTENSIONS, PDF_EXTENSIONS, TEXT_EXTENSIONS
from app.processing.readers import load_metadata_for_artifact, read_raw_file
from app.processing.text_utils import clean_document_text, normalize_text, stable_id
from app.schemas import RawDocument


def ticker_from_path(path: Path) -> str:
    scope = scope_from_path(path)
    if scope.lower() == "market":
        return ""
    return scope.upper()


def scope_from_path(path: Path) -> str:
    try:
        relative = path.relative_to(RAW_DIR)
    except ValueError:
        return "unknown"
    parts = relative.parts
    return parts[1] if len(parts) > 1 else "unknown"


def modality_from_path(path: Path) -> str:
    try:
        category = path.relative_to(RAW_DIR).parts[0]
    except (ValueError, IndexError):
        category = path.parent.name
    if category == "csv":
        return "table"
    if category == "pdf":
        return "pdf"
    if category == "images":
        return "image"
    return "text"


def text_dump_exists(path: Path) -> bool:
    scope = scope_from_path(path)
    text_path = RAW_DIR / "text" / scope / f"{path.stem}.txt"
    return text_path.exists()


def iter_raw_documents(raw_dir: Path = RAW_DIR) -> list[RawDocument]:
    documents: list[RawDocument] = []
    allowed_extensions = TEXT_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS

    for path in raw_dir.rglob("*"):
        if not path.is_file():
            continue
        if "metadata" in path.parts:
            continue
        if path.suffix.lower() == ".html" and text_dump_exists(path):
            continue
        if path.suffix.lower() not in allowed_extensions:
            continue

        text = clean_document_text(normalize_text(read_raw_file(path)))
        if not text:
            continue

        ticker = ticker_from_path(path)
        scope = scope_from_path(path)
        relative = path.relative_to(raw_dir.parent)
        metadata = load_metadata_for_artifact(path, scope)
        documents.append(
            RawDocument(
                id=stable_id(relative.as_posix()),
                text=text,
                source_path=path,
                modality=modality_from_path(path),
                ticker=ticker,
                metadata=metadata,
                scope=scope,
            )
        )
    return documents
