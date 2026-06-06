from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import RAW_DIR


@dataclass(frozen=True)
class IntermarketIndex:
    symbol: str
    name: str
    price: str
    change: str
    change_percent: str
    updated_at: str

    @property
    def trend(self) -> str:
        if self.change.strip().startswith("-") or self.change_percent.strip().startswith("(-"):
            return "decreasing"
        if self.change.strip().startswith("+") or self.change_percent.strip().startswith("(+"):
            return "increasing"
        return "flat/unclear"


TARGET_INDEX_SYMBOLS = ["US 30", "Hang Seng", "Shanghai", "Nikkei 225", "KOSPI"]
INTERMARKET_QUERY_TERMS = [
    "lien thi truong",
    "the gioi",
    "thi truong chung",
    "vn-index",
    "vnindex",
    "dow",
    "hang seng",
    "shanghai",
    "shang hai",
    "nikkei",
    "kospi",
]


def normalize_query(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", str(text).lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_accents).strip()


def is_intermarket_query(question: str) -> bool:
    normalized = normalize_query(question)
    return any(term in normalized for term in INTERMARKET_QUERY_TERMS)


def latest_world_market_text() -> tuple[Path | None, str]:
    market_dir = RAW_DIR / "text" / "market"
    if not market_dir.exists():
        return None, ""

    files = sorted(
        market_dir.glob("*world_market*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None, ""

    path = files[0]
    return path, path.read_text(encoding="utf-8", errors="ignore")


def parse_world_market_indices(text: str) -> list[IntermarketIndex]:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    indexes: list[IntermarketIndex] = []
    for symbol in TARGET_INDEX_SYMBOLS:
        try:
            start = lines.index(symbol)
        except ValueError:
            continue

        row = lines[start : start + 10]
        if len(row) < 6:
            continue
        updated_at = next((value for value in row[6:] if re.match(r"^\d{1,2}:\d{2}:\d{2}$", value)), "")
        indexes.append(
            IntermarketIndex(
                symbol=row[0],
                name=row[2],
                price=row[3],
                change=row[4],
                change_percent=row[5],
                updated_at=updated_at,
            )
        )
    return indexes


def build_intermarket_context(question: str) -> tuple[str, dict | None]:
    if not is_intermarket_query(question):
        return "", None

    path, text = latest_world_market_text()
    indexes = parse_world_market_indices(text)
    if not path or not indexes:
        return "", None

    lines = [
        "Intermarket context from 24HMoney world market page.",
        (
            "Use this as macro/market-background context only, not as a stock ticker. "
            "For Vietnam market inference, treat broad weakness in US/Asia indexes as risk-off pressure, "
            "and broad strength as supportive sentiment."
        ),
    ]
    for item in indexes:
        lines.append(
            f"- {item.symbol} ({item.name}): {item.price}, {item.change} {item.change_percent}, "
            f"trend={item.trend}, updated={item.updated_at}"
        )

    source = {
        "score": 1.0,
        "ticker": "",
        "scope": "market",
        "modality": "text",
        "structure_type": "intermarket_context",
        "heading_path": [],
        "source_path": path.relative_to(RAW_DIR.parent).as_posix(),
        "url": "https://24hmoney.vn/world",
        "artifact_path": path.relative_to(RAW_DIR.parent).as_posix(),
    }
    return "\n".join(lines), source
