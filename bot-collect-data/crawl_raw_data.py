from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
LOGS_DIR = DATA_DIR / "logs"


DEFAULT_TICKERS = ["HPG", "FPT", "VCB"]
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_REPORTS = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
MIN_TABLE_ROWS = 2
MIN_TABLE_COLS = 2
MIN_TABLE_NON_EMPTY_CELLS = 4
MIN_TABLE_FILL_RATIO = 0.4
MIN_UNIQUE_TABLE_VALUES = 3


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self._chunks.append(cleaned)

    def get_text(self) -> str:
        return "\n".join(self._chunks)


class HTMLTableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            self._in_cell = True
            self._current_cell = []
        elif tag == "br" and self._in_cell and self._current_cell is not None:
            self._current_cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._current_row is not None and self._current_cell is not None:
            cell_text = "".join(self._current_cell)
            cell_text = re.sub(r"\s+", " ", cell_text).strip()
            self._current_row.append(cell_text)
            self._current_cell = None
            self._in_cell = False
        elif tag == "tr" and self._current_table is not None and self._current_row is not None:
            if any(cell.strip() for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = None

    def handle_data(self, data: str) -> None:
        if self._in_cell and self._current_cell is not None:
            self._current_cell.append(data)


@dataclass(frozen=True)
class CrawlTarget:
    source: str
    category: str
    url: str
    ticker: str | None
    name: str
    crawl_method: str = "requests"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl and store raw stock/news data into /data/raw."
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=DEFAULT_TICKERS,
        help="Ticker list to crawl. Default: %(default)s",
    )
    parser.add_argument(
        "--include-news",
        action="store_true",
        help="Include ticker news pages from 24hmoney.",
    )
    parser.add_argument(
        "--include-charts",
        action="store_true",
        help="Capture TradingView chart screenshots with Playwright.",
    )
    parser.add_argument(
        "--max-reports",
        type=int,
        default=DEFAULT_MAX_REPORTS,
        help="Maximum 24hmoney analysis report detail pages to crawl per ticker.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.5,
        help="Delay between requests to avoid hitting sources too aggressively.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def setup_directories() -> None:
    for path in [
        RAW_DIR / "html",
        RAW_DIR / "csv",
        RAW_DIR / "pdf",
        RAW_DIR / "images",
        RAW_DIR / "metadata",
        RAW_DIR / "text",
        LOGS_DIR / "crawl_logs",
        LOGS_DIR / "error_logs",
        LOGS_DIR / "scheduler_logs",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("raw_collector")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    crawl_log = LOGS_DIR / "crawl_logs" / f"crawl_{datetime.now():%Y%m%d}.log"
    error_log = LOGS_DIR / "error_logs" / f"error_{datetime.now():%Y%m%d}.log"

    info_handler = logging.FileHandler(crawl_log, encoding="utf-8")
    info_handler.setFormatter(formatter)
    info_handler.setLevel(logging.INFO)

    error_handler = logging.FileHandler(error_log, encoding="utf-8")
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    logger.addHandler(stream_handler)
    return logger


def build_targets(
    tickers: Iterable[str],
    include_news: bool,
    include_charts: bool = False,
) -> list[CrawlTarget]:
    cleaned_tickers = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    targets: list[CrawlTarget] = []

    for ticker in cleaned_tickers:
        targets.extend(
            [
                CrawlTarget(
                    source="24hmoney",
                    category="html",
                    url=f"https://24hmoney.vn/stock/{ticker}",
                    ticker=ticker,
                    name="stock_overview",
                ),
                CrawlTarget(
                    source="vietstock",
                    category="html",
                    url=f"https://finance.vietstock.vn/{ticker}/tai-tai-lieu.htm?doctype=1",
                    ticker=ticker,
                    name="financial_documents",
                ),
                CrawlTarget(
                    source="24hmoney",
                    category="html",
                    url=f"https://24hmoney.vn/bao-cao-phan-tich?k={ticker}",
                    ticker=ticker,
                    name="analysis_report_listing",
                ),
                CrawlTarget(
                    source="vietstock",
                    category="html",
                    url=f"https://finance.vietstock.vn/{ticker}/tin-tuc-su-kien.htm",
                    ticker=ticker,
                    name="ticker_news_events",
                ),
            ]
        )

        if include_news:
            targets.append(
                CrawlTarget(
                    source="24hmoney",
                    category="html",
                    url=f"https://24hmoney.vn/stock/{ticker}/news",
                    ticker=ticker,
                    name="ticker_news",
                )
            )

        if include_charts:
            targets.append(
                CrawlTarget(
                    source="tradingview",
                    category="images",
                    url=f"https://vn.tradingview.com/chart/?symbol=HOSE%3A{ticker}",
                    ticker=ticker,
                    name="chart_screenshot",
                    crawl_method="playwright-screenshot",
                )
            )

    targets.append(
        CrawlTarget(
            source="24hmoney",
            category="html",
            url="https://24hmoney.vn/world",
            ticker=None,
            name="world_market",
        )
    )

    return targets


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_").lower()


def ascii_slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return slugify(ascii_only)


def extract_text_from_html(html_text: str) -> str:
    parser = HTMLTextExtractor()
    parser.feed(html_text)
    return parser.get_text()


def extract_tables_from_html(html_text: str) -> list[list[list[str]]]:
    parser = HTMLTableExtractor()
    parser.feed(html_text)
    return parser.tables


def cleaned_table_rows(table: list[list[str]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in table:
        normalized = [normalize_whitespace(cell) for cell in row]
        if any(cell for cell in normalized):
            cleaned.append(normalized)
    return cleaned


def is_meaningful_table(table: list[list[str]]) -> bool:
    rows = cleaned_table_rows(table)
    if len(rows) < MIN_TABLE_ROWS:
        return False

    max_cols = max((len(row) for row in rows), default=0)
    if max_cols < MIN_TABLE_COLS:
        return False

    non_empty_cells = sum(1 for row in rows for cell in row if cell)
    total_cells = sum(max(len(row), max_cols) for row in rows)
    if non_empty_cells < MIN_TABLE_NON_EMPTY_CELLS or total_cells == 0:
        return False

    fill_ratio = non_empty_cells / total_cells
    if fill_ratio < MIN_TABLE_FILL_RATIO:
        return False

    unique_values = {cell.lower() for row in rows for cell in row if cell}
    if len(unique_values) < MIN_UNIQUE_TABLE_VALUES:
        return False

    data_like_rows = sum(1 for row in rows if sum(1 for cell in row if cell) >= 2)
    return data_like_rows >= 2


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract_first_match(pattern: str, html_text: str) -> str:
    match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return normalize_whitespace(strip_tags(match.group(1)))


def extract_24hmoney_label_value_pairs(html_text: str) -> dict[str, str]:
    label_map = {
        "gia tran": "price_ceiling",
        "gia tc": "reference_price",
        "gia san": "price_floor",
        "nn mua": "foreign_buy_volume",
        "cao nhat": "day_high",
        "trung binh": "average_price",
        "thap nhat": "day_low",
        "nn ban": "foreign_sell_volume",
    }
    pairs: dict[str, str] = {}
    pattern = (
        r'<div[^>]+class="d-row"[^>]*>\s*'
        r'<span[^>]+class="label"[^>]*>(.*?)</span>\s*'
        r'<span[^>]+class="price[^"]*"[^>]*>(.*?)</span>'
    )
    for label, value in re.findall(pattern, html_text, flags=re.IGNORECASE | re.DOTALL):
        raw_label = normalize_whitespace(strip_tags(label))
        cleaned_label = label_map.get(ascii_slugify(raw_label).replace("_", " "), ascii_slugify(raw_label))
        cleaned_value = normalize_whitespace(strip_tags(value))
        if cleaned_label:
            pairs[cleaned_label] = cleaned_value
    return pairs


def extract_24hmoney_bid_offer_levels(html_text: str) -> dict[str, str]:
    row_pattern = r'<div[^>]+class="bid-offer-item"[^>]*>(.*?)</div>\s*</div>'
    rows = re.findall(row_pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
    levels: dict[str, str] = {}
    level_index = 0
    for row_html in rows:
        row_text = normalize_whitespace(strip_tags(row_html)).upper()
        if "KL MUA" in row_text and "GIA MUA" in ascii_slugify(row_text).replace("_", " "):
            continue

        bid_match = re.search(
            r'<div[^>]+class="bid"[^>]*>\s*<span[^>]+class="volumes[^"]*"[^>]*>(.*?)</span>\s*'
            r'<span[^>]+class="price[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        offer_match = re.search(
            r'<div[^>]+class="offer"[^>]*>\s*<span[^>]+class="price[^"]*"[^>]*>(.*?)</span>\s*'
            r'<span[^>]+class="volumes[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not bid_match or not offer_match:
            continue

        level_index += 1
        levels[f"bid_{level_index}_volume"] = normalize_whitespace(strip_tags(bid_match.group(1)))
        levels[f"bid_{level_index}_price"] = normalize_whitespace(strip_tags(bid_match.group(2)))
        levels[f"offer_{level_index}_price"] = normalize_whitespace(strip_tags(offer_match.group(1)))
        levels[f"offer_{level_index}_volume"] = normalize_whitespace(strip_tags(offer_match.group(2)))
        if level_index >= 3:
            break
    return levels


def extract_24hmoney_overview_row(html_text: str, ticker: str, started_at: datetime) -> dict[str, str]:
    label_pairs = extract_24hmoney_label_value_pairs(html_text)
    bid_offer_levels = extract_24hmoney_bid_offer_levels(html_text)

    row = {
        "date": started_at.strftime("%Y-%m-%d"),
        "crawled_at_utc": started_at.isoformat(),
        "ticker": ticker,
        "exchange": extract_first_match(r'<span[^>]+class="stock-exchange"[^>]*>(.*?)</span>', html_text),
        "company_name": extract_first_match(r'<h1[^>]+class="company-name"[^>]*>(.*?)</h1>', html_text),
        "price": extract_first_match(r'<p[^>]+class="price-detail"[^>]*>\s*<span[^>]+class="price"[^>]*>(.*?)</span>', html_text),
        "change": extract_first_match(r'<span[^>]+class="change[^"]*"[^>]*>(.*?)</span>', html_text),
        "change_percent": extract_first_match(r'<span[^>]+class="change-percent[^"]*"[^>]*>(.*?)</span>', html_text),
        "volume": extract_first_match(r'<span[^>]+class="volume"[^>]*>(.*?)</span>', html_text),
        "updated_at": extract_first_match(r'<span[^>]+class="updated-at"[^>]*>(.*?)</span>', html_text),
        "total_bid_volume": extract_first_match(r'<div[^>]+class="bid-volumes"[^>]*>.*?<span[^>]+class="volumes val green"[^>]*>(.*?)</span>', html_text),
        "total_offer_volume": extract_first_match(r'<div[^>]+class="offer-volumes"[^>]*>.*?<span[^>]+class="volumes val red"[^>]*>(.*?)</span>', html_text),
    }
    row.update(label_pairs)
    row.update(bid_offer_levels)
    return row


def append_24hmoney_overview_timeseries_csv(
    html_text: str,
    target: CrawlTarget,
    started_at: datetime,
) -> list[str]:
    if not target.ticker:
        return []

    csv_dir = RAW_DIR / "csv" / target.ticker
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / "stock_overview_timeseries.csv"
    row = extract_24hmoney_overview_row(html_text, target.ticker, started_at)

    existing_fieldnames: list[str] = []
    existing_rows: list[dict[str, str]] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            existing_fieldnames = reader.fieldnames or []
            existing_rows = list(reader)

    fieldnames = list(dict.fromkeys(existing_fieldnames + list(row.keys())))
    if not existing_fieldnames:
        fieldnames = list(row.keys())

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for existing_row in existing_rows:
            writer.writerow({field: existing_row.get(field, "") for field in fieldnames})
        writer.writerow({field: row.get(field, "") for field in fieldnames})

    return [str(csv_path.relative_to(PROJECT_ROOT)).replace("\\", "/")]


def detect_storage_category(content_type: str, fallback_category: str) -> str:
    lowered = content_type.lower()
    if "application/json" in lowered or lowered.endswith("+json"):
        return "api"
    if "application/pdf" in lowered:
        return "pdf"
    if lowered.startswith("image/"):
        return "images"
    return fallback_category


def resolve_extension(content_type: str, parsed_url_path: str, category: str) -> str:
    lowered = content_type.lower()
    if "application/json" in lowered or lowered.endswith("+json"):
        return ".json"
    if "text/csv" in lowered or parsed_url_path.endswith(".csv"):
        return ".csv"
    if "application/pdf" in lowered or parsed_url_path.endswith(".pdf"):
        return ".pdf"
    if lowered.startswith("image/"):
        subtype = lowered.split("/", 1)[1].split(";", 1)[0]
        return f".{subtype}"
    if category == "html":
        return ".html"
    return Path(parsed_url_path).suffix or ".bin"


def write_table_csvs(
    html_text: str,
    target: CrawlTarget,
    timestamp: str,
) -> tuple[list[str], dict[str, int]]:
    if target.source == "24hmoney" and target.name == "stock_overview":
        return [], {"table_candidates": 0, "tables_saved": 0, "tables_skipped": 0}

    tables = extract_tables_from_html(html_text)
    if not tables:
        return [], {"table_candidates": 0, "tables_saved": 0, "tables_skipped": 0}

    scope = target.ticker or "market"
    csv_dir = RAW_DIR / "csv" / scope
    csv_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[str] = []
    skipped_count = 0
    for index, table in enumerate(tables, start=1):
        cleaned_rows = cleaned_table_rows(table)
        if not is_meaningful_table(cleaned_rows):
            skipped_count += 1
            continue

        max_cols = max((len(row) for row in cleaned_rows), default=0)
        if max_cols == 0:
            continue

        csv_path = csv_dir / (
            f"{timestamp}__{slugify(target.source)}__{slugify(target.name)}__table_{index:02d}.csv"
        )
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            for row in cleaned_rows:
                padded = row + [""] * (max_cols - len(row))
                writer.writerow(padded)
        written_paths.append(str(csv_path.relative_to(PROJECT_ROOT)).replace("\\", "/"))

    return written_paths, {
        "table_candidates": len(tables),
        "tables_saved": len(written_paths),
        "tables_skipped": skipped_count,
    }


def save_artifacts(
    target: CrawlTarget,
    response: requests.Response,
    started_at: datetime,
) -> dict:
    content_type = response.headers.get("Content-Type", "")
    storage_category = detect_storage_category(content_type, target.category)
    parsed_path = urlparse(target.url).path
    extension = resolve_extension(content_type, parsed_path, storage_category)
    scope = target.ticker or "market"
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    stem = f"{timestamp}__{slugify(target.source)}__{slugify(target.name)}"

    artifact_dir = RAW_DIR / storage_category / scope
    metadata_dir = RAW_DIR / "metadata" / scope
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    raw_path = artifact_dir / f"{stem}{extension}"
    metadata_path = metadata_dir / f"{stem}.metadata.json"

    if storage_category in {"html", "api"} and extension in {".html", ".json", ".csv"}:
        raw_path.write_text(response.text, encoding="utf-8")
    else:
        raw_path.write_bytes(response.content)

    text_path: Path | None = None
    csv_paths: list[str] = []
    table_stats = {"table_candidates": 0, "tables_saved": 0, "tables_skipped": 0}
    if storage_category == "html":
        text_dir = RAW_DIR / "text" / scope
        text_dir.mkdir(parents=True, exist_ok=True)
        text_path = text_dir / f"{stem}.txt"
        extracted_text = extract_text_from_html(response.text)
        text_path.write_text(extracted_text, encoding="utf-8")
        csv_paths, table_stats = write_table_csvs(response.text, target, timestamp)
        if target.source == "24hmoney" and target.name == "stock_overview":
            csv_paths = append_24hmoney_overview_timeseries_csv(
                response.text,
                target,
                started_at,
            )
            table_stats = {"table_candidates": 0, "tables_saved": len(csv_paths), "tables_skipped": 0}

    metadata = {
        "source": target.source,
        "category": storage_category,
        "ticker": target.ticker,
        "name": target.name,
        "url": target.url,
        "crawl_method": target.crawl_method,
        "crawled_at_utc": started_at.isoformat(),
        "status_code": response.status_code,
        "content_type": content_type,
        "artifact_path": str(raw_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "text_path": (
            str(text_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            if text_path
            else None
        ),
        "csv_paths": csv_paths,
        "text_length": len(extracted_text) if storage_category == "html" else None,
        **table_stats,
        "content_length": len(response.content),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def extract_24hmoney_report_links(html_text: str, ticker: str) -> list[str]:
    pattern = r'href="(/bao-cao-phan-tich/[^"]+rpId\d+\.html)"'
    links = []
    for match in re.findall(pattern, html_text):
        absolute = urljoin("https://24hmoney.vn", html.unescape(match))
        if f"/{ticker.lower()}-" in absolute.lower():
            links.append(absolute)
    return list(dict.fromkeys(links))


def extract_24hmoney_pdf_link(html_text: str) -> str | None:
    match = re.search(r'url_file:"([^"]+\.pdf)"', html_text)
    if not match:
        return None
    return html.unescape(match.group(1).replace("\\u002F", "/"))


def extract_vietstock_document_links(html_text: str) -> list[str]:
    links: list[str] = []
    for match in re.findall(r'href=["\']([^"\']+\.(?:pdf|zip|xls|xlsx|doc|docx))["\']', html_text, flags=re.IGNORECASE):
        links.append(urljoin("https://finance.vietstock.vn", html.unescape(match)))
    return list(dict.fromkeys(links))


def save_binary_artifact(
    source: str,
    category: str,
    ticker: str | None,
    name: str,
    url: str,
    content: bytes,
    content_type: str,
    crawl_method: str,
    started_at: datetime,
) -> dict:
    scope = ticker or "market"
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    parsed_path = urlparse(url).path
    extension = resolve_extension(content_type, parsed_path, category)
    stem = f"{timestamp}__{slugify(source)}__{slugify(name)}"

    artifact_dir = RAW_DIR / category / scope
    metadata_dir = RAW_DIR / "metadata" / scope
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    raw_path = artifact_dir / f"{stem}{extension}"
    metadata_path = metadata_dir / f"{stem}.metadata.json"

    raw_path.write_bytes(content)
    metadata = {
        "source": source,
        "category": category,
        "ticker": ticker,
        "name": name,
        "url": url,
        "crawl_method": crawl_method,
        "crawled_at_utc": started_at.isoformat(),
        "content_type": content_type,
        "artifact_path": str(raw_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "content_length": len(content),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def crawl_follow_up_documents(
    session: requests.Session,
    html_target: CrawlTarget,
    response: requests.Response,
    max_reports: int,
    timeout: int,
    delay_seconds: float,
    logger: logging.Logger,
    seen_follow_up_urls: set[str] | None = None,
) -> list[dict]:
    if not html_target.ticker:
        return []

    follow_up_results: list[dict] = []

    if html_target.source == "24hmoney" and html_target.name in {
        "stock_overview",
        "analysis_report_listing",
    }:
        report_links = extract_24hmoney_report_links(response.text, html_target.ticker)[:max_reports]
        artifact_prefix = (
            "analysis_report_listing"
            if html_target.name == "analysis_report_listing"
            else "analysis_report"
        )
        for index, report_url in enumerate(report_links, start=1):
            if seen_follow_up_urls is not None and report_url in seen_follow_up_urls:
                logger.info("Skip duplicate follow-up report %s", report_url)
                continue
            detail_target = CrawlTarget(
                source="24hmoney",
                category="html",
                url=report_url,
                ticker=html_target.ticker,
                name=f"{artifact_prefix}_detail_{index:02d}",
            )
            started_at = datetime.now(timezone.utc)
            try:
                if seen_follow_up_urls is not None:
                    seen_follow_up_urls.add(report_url)
                detail_response = session.get(report_url, timeout=timeout)
                detail_response.raise_for_status()
                detail_metadata = save_artifacts(detail_target, detail_response, started_at)
                follow_up_results.append({"status": "success", **detail_metadata})
                logger.info("Stored report detail %s", detail_metadata["artifact_path"])

                pdf_url = extract_24hmoney_pdf_link(detail_response.text)
                if pdf_url:
                    if seen_follow_up_urls is not None and pdf_url in seen_follow_up_urls:
                        logger.info("Skip duplicate follow-up PDF %s", pdf_url)
                        continue
                    pdf_started_at = datetime.now(timezone.utc)
                    if seen_follow_up_urls is not None:
                        seen_follow_up_urls.add(pdf_url)
                    pdf_response = session.get(pdf_url, timeout=timeout)
                    pdf_response.raise_for_status()
                    pdf_metadata = save_binary_artifact(
                        source="24hmoney",
                        category="pdf",
                        ticker=html_target.ticker,
                        name=f"{artifact_prefix}_pdf_{index:02d}",
                        url=pdf_url,
                        content=pdf_response.content,
                        content_type=pdf_response.headers.get("Content-Type", "application/pdf"),
                        crawl_method="requests-follow-up",
                        started_at=pdf_started_at,
                    )
                    follow_up_results.append({"status": "success", **pdf_metadata})
                    logger.info("Stored report PDF %s", pdf_metadata["artifact_path"])
            except Exception as exc:  # noqa: BLE001
                follow_up_results.append(
                    {
                        "status": "error",
                        "source": detail_target.source,
                        "ticker": detail_target.ticker,
                        "name": detail_target.name,
                        "url": detail_target.url,
                        "error": str(exc),
                        "crawled_at_utc": started_at.isoformat(),
                    }
                )
                logger.error("Failed follow-up crawl %s | %s", detail_target.url, exc)

            if delay_seconds > 0 and index < len(report_links):
                time.sleep(delay_seconds)

    if html_target.source == "vietstock" and html_target.name == "financial_documents":
        for index, document_url in enumerate(extract_vietstock_document_links(response.text), start=1):
            if seen_follow_up_urls is not None and document_url in seen_follow_up_urls:
                logger.info("Skip duplicate Vietstock document %s", document_url)
                continue
            started_at = datetime.now(timezone.utc)
            try:
                if seen_follow_up_urls is not None:
                    seen_follow_up_urls.add(document_url)
                document_response = session.get(document_url, timeout=timeout)
                document_response.raise_for_status()
                category = detect_storage_category(
                    document_response.headers.get("Content-Type", ""),
                    "pdf",
                )
                metadata = save_binary_artifact(
                    source="vietstock",
                    category=category,
                    ticker=html_target.ticker,
                    name=f"financial_document_{index:02d}",
                    url=document_url,
                    content=document_response.content,
                    content_type=document_response.headers.get("Content-Type", ""),
                    crawl_method="requests-follow-up",
                    started_at=started_at,
                )
                follow_up_results.append({"status": "success", **metadata})
                logger.info("Stored Vietstock document %s", metadata["artifact_path"])
            except Exception as exc:  # noqa: BLE001
                follow_up_results.append(
                    {
                        "status": "error",
                        "source": "vietstock",
                        "ticker": html_target.ticker,
                        "name": f"financial_document_{index:02d}",
                        "url": document_url,
                        "error": str(exc),
                        "crawled_at_utc": started_at.isoformat(),
                    }
                )
                logger.error("Failed document download %s | %s", document_url, exc)

    return follow_up_results


def capture_chart_screenshot(
    target: CrawlTarget,
    timeout: int,
    logger: logging.Logger,
) -> dict:
    started_at = datetime.now(timezone.utc)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for chart screenshots. "
            "Install it with `pip install playwright` and `playwright install chromium`."
        ) from exc

    logger.info("Capturing chart screenshot %s", target.url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.goto(target.url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(3000)
            content = page.screenshot(full_page=True, type="png")
        finally:
            browser.close()

    return save_binary_artifact(
        source=target.source,
        category="images",
        ticker=target.ticker,
        name=target.name,
        url=target.url,
        content=content,
        content_type="image/png",
        crawl_method=target.crawl_method,
        started_at=started_at,
    )


def crawl_targets(
    session: requests.Session,
    targets: list[CrawlTarget],
    delay_seconds: float,
    timeout: int,
    max_reports: int,
    logger: logging.Logger,
) -> dict:
    summary: dict[str, object] = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_targets": len(targets),
        "success_count": 0,
        "error_count": 0,
        "results": [],
    }
    seen_follow_up_urls: set[str] = set()

    for index, target in enumerate(targets, start=1):
        started_at = datetime.now(timezone.utc)
        logger.info("[%s/%s] Crawling %s", index, len(targets), target.url)

        try:
            if target.crawl_method == "playwright-screenshot":
                metadata = capture_chart_screenshot(target, timeout, logger)
                summary["success_count"] = int(summary["success_count"]) + 1
                summary["results"].append({"status": "success", **metadata})
                logger.info("Stored screenshot for %s at %s", target.url, metadata["artifact_path"])
            else:
                response = session.get(target.url, timeout=timeout)
                response.raise_for_status()
                metadata = save_artifacts(target, response, started_at)
                summary["success_count"] = int(summary["success_count"]) + 1
                summary["results"].append({"status": "success", **metadata})
                logger.info("Stored raw artifact for %s at %s", target.url, metadata["artifact_path"])

                follow_up_results = crawl_follow_up_documents(
                    session=session,
                    html_target=target,
                    response=response,
                    max_reports=max_reports,
                    timeout=timeout,
                    delay_seconds=delay_seconds,
                    logger=logger,
                    seen_follow_up_urls=seen_follow_up_urls,
                )
                for record in follow_up_results:
                    summary["results"].append(record)
                    if record["status"] == "success":
                        summary["success_count"] = int(summary["success_count"]) + 1
                    else:
                        summary["error_count"] = int(summary["error_count"]) + 1
        except Exception as exc:  # noqa: BLE001
            error_record = {
                "status": "error",
                "source": target.source,
                "ticker": target.ticker,
                "name": target.name,
                "url": target.url,
                "error": str(exc),
                "crawled_at_utc": started_at.isoformat(),
            }
            summary["error_count"] = int(summary["error_count"]) + 1
            summary["results"].append(error_record)
            logger.error("Failed to crawl %s | %s", target.url, exc)

        if index < len(targets) and delay_seconds > 0:
            time.sleep(delay_seconds)

    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return summary


def write_run_summary(summary: dict) -> Path:
    finished_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = LOGS_DIR / "crawl_logs" / f"run_summary_{finished_at}.json"
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def run_collector(
    tickers: Iterable[str] = DEFAULT_TICKERS,
    include_news: bool = False,
    include_charts: bool = False,
    max_reports: int = DEFAULT_MAX_REPORTS,
    delay_seconds: float = 1.5,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    setup_directories()
    logger = setup_logger()

    targets = build_targets(tickers, include_news, include_charts)
    if not targets:
        logger.error("No crawl targets were generated. Please provide valid tickers.")
        return {
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_targets": 0,
            "success_count": 0,
            "error_count": 1,
            "results": [],
            "error": "No crawl targets were generated.",
        }

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    summary = crawl_targets(
        session=session,
        targets=targets,
        delay_seconds=delay_seconds,
        timeout=timeout,
        max_reports=max_reports,
        logger=logger,
    )
    summary_path = write_run_summary(summary)
    summary["summary_path"] = str(summary_path.relative_to(PROJECT_ROOT)).replace("\\", "/")

    logger.info(
        "Finished crawl. success=%s error=%s summary=%s",
        summary["success_count"],
        summary["error_count"],
        summary["summary_path"],
    )
    return summary


def main() -> int:
    args = parse_args()
    summary = run_collector(
        tickers=args.tickers,
        include_news=args.include_news,
        include_charts=args.include_charts,
        max_reports=args.max_reports,
        delay_seconds=args.delay_seconds,
        timeout=args.timeout,
    )
    return 0 if int(summary["error_count"]) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
