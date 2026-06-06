from __future__ import annotations

from html.parser import HTMLParser

from app.processing.text_utils import (
    looks_like_heading,
    looks_like_table,
    looks_like_widget,
    normalize_text,
    rows_to_table_text,
)
from app.schemas import RawDocument, StructureBlock


class HTMLStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[StructureBlock] = []
        self.heading_path: list[str] = []
        self._tag_stack: list[str] = []
        self._capture_tag: str | None = None
        self._capture_parts: list[str] = []
        self._table_depth = 0
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag)
        if tag == "table":
            self._flush_capture()
            self._table_depth += 1
            self._table_rows = []
        elif self._table_depth and tag == "tr":
            self._current_row = []
        elif self._table_depth and tag in {"td", "th"}:
            self._current_cell = []
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}:
            self._flush_capture()
            self._capture_tag = tag
            self._capture_parts = []
        elif tag == "br" and self._capture_tag:
            self._capture_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._table_depth and tag in {"td", "th"} and self._current_cell is not None:
            cell = normalize_text(" ".join(self._current_cell))
            if self._current_row is not None:
                self._current_row.append(cell)
            self._current_cell = None
        elif self._table_depth and tag == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self._table_rows.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            table_text = rows_to_table_text(self._table_rows)
            if table_text:
                self.blocks.append(
                    StructureBlock(
                        text=table_text,
                        structure_type="table",
                        heading_path=list(self.heading_path),
                        metadata={"row_count": len(self._table_rows)},
                    )
                )
            self._table_rows = []
        elif tag == self._capture_tag:
            self._flush_capture()

        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)
        elif self._capture_tag:
            self._capture_parts.append(data)

    def _flush_capture(self) -> None:
        if not self._capture_tag:
            return

        text = normalize_text(" ".join(self._capture_parts))
        tag = self._capture_tag
        self._capture_tag = None
        self._capture_parts = []
        if not text:
            return

        if tag.startswith("h"):
            level = int(tag[1])
            self.heading_path = self.heading_path[: level - 1] + [text]
            self.blocks.append(
                StructureBlock(
                    text=text,
                    structure_type="heading",
                    heading_path=list(self.heading_path),
                    metadata={"heading_level": level},
                )
            )
            return

        self.blocks.append(
            StructureBlock(
                text=text,
                structure_type="paragraph",
                heading_path=list(self.heading_path),
                metadata={"html_tag": tag},
            )
        )


def parse_text_blocks(text: str) -> list[StructureBlock]:
    blocks: list[StructureBlock] = []
    heading_path: list[str] = []
    paragraph_lines: list[str] = []
    table_lines: list[str] = []
    widget_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        paragraph = normalize_text("\n".join(paragraph_lines))
        paragraph_lines = []
        if paragraph:
            blocks.append(StructureBlock(paragraph, "paragraph", list(heading_path), {}))

    def flush_table() -> None:
        nonlocal table_lines
        table = normalize_text("\n".join(table_lines))
        table_lines = []
        if table:
            blocks.append(StructureBlock(table, "table", list(heading_path), {}))

    def flush_widget() -> None:
        nonlocal widget_lines
        widget = normalize_text("\n".join(widget_lines))
        widget_lines = []
        if widget:
            blocks.append(StructureBlock(widget, "widget", list(heading_path), {}))

    for raw_line in text.splitlines():
        line = normalize_text(raw_line)
        if not line:
            flush_paragraph()
            flush_table()
            flush_widget()
            continue
        if looks_like_heading(line):
            flush_paragraph()
            flush_table()
            flush_widget()
            heading = line.lstrip("#").strip()
            heading_path = [heading]
            blocks.append(
                StructureBlock(
                    heading,
                    "heading",
                    list(heading_path),
                    {"heading_level": 1},
                )
            )
        elif looks_like_table(line):
            flush_paragraph()
            flush_widget()
            table_lines.append(line)
        elif looks_like_widget(line):
            flush_paragraph()
            flush_table()
            widget_lines.append(line)
        else:
            flush_table()
            flush_widget()
            paragraph_lines.append(line)

    flush_paragraph()
    flush_table()
    flush_widget()
    return blocks


def parse_document_structures(document: RawDocument, csv_rows: list[list[str]] | None = None) -> list[StructureBlock]:
    suffix = document.source_path.suffix.lower()
    if suffix == ".html":
        parser = HTMLStructureParser()
        parser.feed(document.text)
        parser._flush_capture()
        if parser.blocks:
            return parser.blocks
    if suffix == ".csv":
        rows = csv_rows or []
        table = rows_to_table_text(rows)
        return [
            StructureBlock(
                table,
                "table",
                [],
                {"row_count": len(rows), "source_format": "csv"},
            )
        ]
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return [
            StructureBlock(
                document.text,
                "widget",
                [],
                {"source_format": "image"},
            )
        ]
    return parse_text_blocks(document.text)
