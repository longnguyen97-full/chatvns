from __future__ import annotations

import hashlib
import html
import re
import uuid

from app.processing.constants import BOILERPLATE_LINES, TOKEN_PATTERN


def stable_id(*parts: str) -> str:
    joined = "|".join(parts)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)


def token_count(text: str) -> int:
    return len(tokenize(text))


def detokenize(tokens: list[str]) -> str:
    text = " ".join(tokens)
    text = re.sub(r"\s+([,.;:!?%)\]\}])", r"\1", text)
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    return text.strip()


def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def rows_to_table_text(rows: list[list[str]]) -> str:
    lines = []
    for row in rows:
        cleaned = [normalize_text(cell) for cell in row if normalize_text(cell)]
        if cleaned:
            lines.append(" | ".join(cleaned))
    return "\n".join(lines)


def looks_like_heading(line: str) -> bool:
    if line.startswith("#"):
        return True
    if len(line) > 90 or len(tokenize(line)) > 14:
        return False
    if re.match(r"^\d+[\).\s-]+", line):
        return True
    letters = re.sub(r"[^A-Za-zÀ-ỹ]", "", line)
    return bool(letters) and letters.upper() == letters and len(letters) >= 3


def looks_like_table(line: str) -> bool:
    return line.count("|") >= 2 or line.count(",") >= 4 or "\t" in line


def looks_like_widget(line: str) -> bool:
    key_value = bool(re.search(r"[:：]\s*\S+", line))
    numeric_dense = len(re.findall(r"\d+(?:[.,]\d+)?%?", line)) >= 3
    return key_value or numeric_dense


def is_noise_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return True
    if lowered in BOILERPLATE_LINES:
        return True
    if lowered.startswith(("window[", "function ", "var ", "const ", "let ")):
        return True
    if "googletagmanager.com" in lowered or "_gtm_" in lowered:
        return True
    if lowered.startswith(("{", "};", "])", "</", "<script")) and len(line) > 40:
        return True
    if "quét mã qr" in lowered or "cài đặt tiện ích" in lowered:
        return True
    if "số giấy phép mạng xã hội" in lowered or "chịu trách nhiệm nội dung" in lowered:
        return True
    return False


def clean_document_text(text: str) -> str:
    lines = [line for line in text.splitlines() if not is_noise_line(normalize_text(line))]
    return normalize_text("\n".join(lines))
