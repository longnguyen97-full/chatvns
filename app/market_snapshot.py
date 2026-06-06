from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.config import RAW_DIR


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    path: Path
    row: dict[str, str]


def normalize_query(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_accents).strip()


def is_market_snapshot_query(question: str) -> bool:
    normalized = normalize_query(question)
    terms = [
        "gia",
        "price",
        "hom nay",
        "hien tai",
        "dang tang",
        "dang giam",
        "khoi luong",
        "thanh khoan",
    ]
    return any(term in normalized for term in terms)


def is_quick_summary_query(question: str) -> bool:
    normalized = normalize_query(question)
    terms = ["tom tat", "summary", "quick", "nhanh", "tong quan"]
    return any(term in normalized for term in terms)


def load_latest_market_snapshot(ticker: str | None) -> MarketSnapshot | None:
    if not ticker:
        return None

    path = RAW_DIR / "csv" / ticker.upper() / "stock_overview_timeseries.csv"
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None

    return MarketSnapshot(ticker=ticker.upper(), path=path, row=rows[-1])


def build_market_snapshot_context(snapshot: MarketSnapshot | None) -> str:
    if not snapshot:
        return ""

    row = snapshot.row
    fields = [
        ("ticker", "Ticker"),
        ("company_name", "Company"),
        ("exchange", "Exchange"),
        ("price", "Current price"),
        ("change", "Change"),
        ("change_percent", "Change percent"),
        ("volume", "Volume"),
        ("updated_at", "Updated at"),
        ("day_high", "Day high"),
        ("day_low", "Day low"),
        ("reference_price", "Reference price"),
        ("price_ceiling", "Ceiling price"),
        ("price_floor", "Floor price"),
        ("foreign_buy_volume", "Foreign buy volume"),
        ("foreign_sell_volume", "Foreign sell volume"),
        ("bid_1_price", "Best bid"),
        ("offer_1_price", "Best offer"),
    ]

    lines = [
        f"Market snapshot source: {snapshot.path.relative_to(RAW_DIR.parent).as_posix()}",
        (
            "Use this snapshot as the primary source for questions about current/latest price, "
            "change, volume or liquidity. Do not confuse current price with analyst target price."
        ),
    ]
    for key, label in fields:
        value = row.get(key)
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def compact_text(text: str, limit: int = 160) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def sentence_candidates(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if not normalized:
        return []
    return [
        sentence.strip(" -:\t")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", normalized)
        if len(sentence.strip()) >= 40
    ]


def normalized_contains_any(text: str, terms: list[str]) -> bool:
    normalized = normalize_query(text)
    return any(term in normalized for term in terms)


def extract_bullets(chunks, terms: list[str], limit: int = 2) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for chunk in chunks or []:
        for sentence in sentence_candidates(getattr(chunk, "text", "")):
            if not normalized_contains_any(sentence, terms):
                continue
            bullet = compact_text(sentence)
            key = bullet.lower()
            if key in seen:
                continue
            seen.add(key)
            bullets.append(bullet)
            if len(bullets) >= limit:
                return bullets
    return bullets


def source_bullets(snapshot: MarketSnapshot | None, chunks, limit: int = 4) -> list[str]:
    sources: list[str] = []
    seen: set[str] = set()
    if snapshot:
        snapshot_source = snapshot.path.relative_to(RAW_DIR.parent).as_posix()
        sources.append(f"{snapshot_source} | https://24hmoney.vn/stock/{snapshot.ticker}")
        seen.add(snapshot_source)

    for chunk in chunks or []:
        source_path = str(getattr(chunk, "source_path", ""))
        if not source_path or source_path in seen:
            continue
        seen.add(source_path)
        sources.append(source_path)
        if len(sources) >= limit:
            break
    return sources


def compressed_quick_summary_context(snapshot: MarketSnapshot | None, chunks, max_chunks: int = 3) -> str:
    lines: list[str] = []
    if snapshot:
        lines.append("Market snapshot:")
        lines.append(build_market_snapshot_context(snapshot))

    selected_chunks = list(chunks or [])[:max_chunks]
    if selected_chunks:
        lines.append("Retrieved context previews:")
    for index, chunk in enumerate(selected_chunks, start=1):
        heading = " > ".join(getattr(chunk, "heading_path", []) or [])
        lines.extend(
            [
                f"[{index}] ticker={getattr(chunk, 'ticker', '')} score={getattr(chunk, 'score', 0):.4f}",
                f"source={getattr(chunk, 'source_path', '')}",
                f"heading={heading}",
                compact_text(getattr(chunk, "text", ""), limit=900),
            ]
        )
    return "\n".join(lines)


def trend_from_snapshot(row: dict[str, str]) -> str:
    change = (row.get("change") or "").strip()
    change_percent = (row.get("change_percent") or "").strip()
    if change.startswith("-") or change_percent.startswith("-"):
        return "Ngắn hạn đang giảm theo snapshot gần nhất."
    if change and not change.startswith("0"):
        return "Ngắn hạn đang tăng theo snapshot gần nhất."
    return "Ngắn hạn đi ngang/chưa có biến động rõ theo snapshot gần nhất."


def format_quick_stock_summary(snapshot: MarketSnapshot | None, chunks=None, ticker: str | None = None) -> str:
    resolved_ticker = (ticker or (snapshot.ticker if snapshot else "")).upper()
    row = snapshot.row if snapshot else {}
    price = row.get("price") or "chưa có dữ liệu"
    change_percent = row.get("change_percent") or ""
    volume = row.get("volume") or "chưa có dữ liệu"
    price_line = f"{price} {change_percent}" if change_percent else price

    highlights = extract_bullets(
        chunks,
        ["tang truong", "trien vong", "khuyen nghi", "loi nhuan", "doanh thu", "dong luc", "tich cuc", "muc tieu", "du an"],
    )
    risks = extract_bullets(
        chunks,
        ["rui ro", "ap luc", "kho khan", "suy giam", "bien dong", "canh tranh", "no", "chi phi"],
    )

    if not highlights:
        highlights = [
            compact_text(getattr(chunk, "text", ""), limit=150)
            for chunk in (chunks or [])[:2]
            if compact_text(getattr(chunk, "text", ""), limit=150)
        ]
    if not highlights:
        highlights = ["Chưa tìm thấy điểm nổi bật rõ ràng trong context retrieved."]
    if not risks:
        risks = ["Context hiện tại chưa nêu rủi ro cụ thể; cần đọc thêm báo cáo/tin tức liên quan."]

    lines = [
        f"## {resolved_ticker} - Tóm tắt nhanh",
        "",
        f"- Giá hiện tại: {price_line}",
        f"- Thanh khoản: {volume}",
        f"- Xu hướng ngắn hạn: {trend_from_snapshot(row)}",
        "- Điểm nổi bật:",
    ]
    lines.extend(f"  - {bullet}" for bullet in highlights)
    lines.append("- Rủi ro cần lưu ý:")
    lines.extend(f"  - {bullet}" for bullet in risks)
    lines.append("- Nguồn:")
    lines.extend(f"  - {source}" for source in source_bullets(snapshot, chunks))
    return "\n".join(lines)


def format_market_snapshot_answer(snapshot: MarketSnapshot) -> str:
    row = snapshot.row
    ticker = snapshot.ticker
    price = row.get("price") or "chưa có"
    change = row.get("change") or ""
    change_percent = row.get("change_percent") or ""
    volume = row.get("volume") or ""
    updated_at = row.get("updated_at") or row.get("crawled_at_utc") or ""
    company_name = row.get("company_name") or ticker

    direction = ""
    if change.strip().startswith("-"):
        direction = "giảm"
    elif change.strip() and not change.strip().startswith("0"):
        direction = "tăng"

    parts = [f"{ticker} ({company_name}) đang có giá {price}."]
    if direction or change or change_percent:
        movement = " ".join(part for part in [direction, change, change_percent] if part)
        parts.append(f"Biến động: {movement}.")
    if volume:
        parts.append(f"Khối lượng: {volume}.")
    if updated_at:
        parts.append(f"Dữ liệu cập nhật: {updated_at}.")
    parts.append(f"Nguồn: https://24hmoney.vn/stock/{ticker}.")
    return "\n\n".join(parts)
