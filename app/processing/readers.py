from __future__ import annotations

import csv
import json
from pathlib import Path

from app.config import RAW_DIR
from app.processing.constants import IMAGE_EXTENSIONS, PDF_EXTENSIONS
from app.processing.text_utils import rows_to_table_text


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.reader(handle)]


def read_pdf_text(path: Path) -> str:
    try:
        import fitz

        document = fitz.open(str(path))
        try:
            text = "\n".join(page.get_text("text") or "" for page in document)
        finally:
            document.close()
    except Exception as exc:  # noqa: BLE001
        return f"[PDF artifact without extracted text] {path.name} | pymupdf_error={exc}"
    if text.strip():
        return text
    return f"[PDF artifact without extracted text] {path.name}"


def read_raw_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return rows_to_table_text(read_csv_rows(path))
    if suffix in PDF_EXTENSIONS:
        return read_pdf_text(path)
    if suffix in IMAGE_EXTENSIONS:
        return f"[Image artifact] {path.name}"
    return path.read_text(encoding="utf-8", errors="ignore")


def load_metadata_for_artifact(path: Path, ticker: str) -> dict:
    stem = path.stem
    candidates = sorted((RAW_DIR / "metadata" / ticker).glob(f"{stem}.metadata.json"))
    if not candidates:
        return {}
    try:
        return json.loads(candidates[0].read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
