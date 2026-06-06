from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass

from app.config import RAW_DIR


TECHNICAL_QUERY_PATTERN = re.compile(
    r"\b(ptkt|kỹ thuật|ky thuat|rsi|macd|bollinger|ma\d*|sma|ema|"
    r"đường trung bình|duong trung binh|hỗ trợ|ho tro|kháng cự|khang cu|"
    r"xu hướng|xu huong|chỉ báo|chi bao)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class OHLCVRow:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def is_technical_query(question: str) -> bool:
    return bool(TECHNICAL_QUERY_PATTERN.search(question))


def parse_number(value: str) -> float | None:
    cleaned = re.sub(r"[^\d,.\-]", "", value or "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_header(header: str) -> str:
    lowered = header.strip().lower()
    mapping = {
        "ngày": "date",
        "date": "date",
        "time": "date",
        "open": "open",
        "mở cửa": "open",
        "high": "high",
        "cao nhất": "high",
        "low": "low",
        "thấp nhất": "low",
        "close": "close",
        "đóng cửa": "close",
        "giá": "close",
        "volume": "volume",
        "kl": "volume",
        "klgd": "volume",
    }
    return mapping.get(lowered, lowered)


def load_ohlcv_rows(ticker: str) -> list[OHLCVRow]:
    rows: list[OHLCVRow] = []
    csv_dir = RAW_DIR / "csv" / ticker.upper()
    if not csv_dir.exists():
        return rows

    for path in csv_dir.glob("*.csv"):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                continue
            field_map = {field: normalize_header(field) for field in reader.fieldnames}
            normalized_fields = set(field_map.values())
            required = {"date", "open", "high", "low", "close", "volume"}
            if not required.issubset(normalized_fields):
                continue

            for row in reader:
                normalized = {field_map[key]: value for key, value in row.items() if key in field_map}
                parsed = {
                    key: parse_number(normalized.get(key, ""))
                    for key in ["open", "high", "low", "close", "volume"]
                }
                if any(value is None for value in parsed.values()):
                    continue
                rows.append(
                    OHLCVRow(
                        date=str(normalized.get("date", "")),
                        open=float(parsed["open"] or 0),
                        high=float(parsed["high"] or 0),
                        low=float(parsed["low"] or 0),
                        close=float(parsed["close"] or 0),
                        volume=float(parsed["volume"] or 0),
                    )
                )
    return rows


def simple_moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def rsi(values: list[float], window: int = 14) -> float | None:
    if len(values) <= window:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-window - 1 : -1], values[-window:]):
        delta = current - previous
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    average_gain = sum(gains) / window
    average_loss = sum(losses) / window
    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def ema_series(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (window + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def macd(values: list[float]) -> tuple[float, float, float] | None:
    if len(values) < 35:
        return None
    ema12 = ema_series(values, 12)
    ema26 = ema_series(values, 26)
    macd_line = [short - long for short, long in zip(ema12[-len(ema26) :], ema26)]
    signal_line = ema_series(macd_line, 9)
    histogram = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], histogram


def bollinger(values: list[float], window: int = 20) -> tuple[float, float, float] | None:
    if len(values) < window:
        return None
    recent = values[-window:]
    middle = sum(recent) / window
    variance = sum((value - middle) ** 2 for value in recent) / window
    std = math.sqrt(variance)
    return middle - 2 * std, middle, middle + 2 * std


def latest_snapshot_context(ticker: str) -> str:
    path = RAW_DIR / "csv" / ticker.upper() / "stock_overview_timeseries.csv"
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return ""
    row = rows[-1]
    fields = [
        "date",
        "price",
        "change",
        "change_percent",
        "volume",
        "day_high",
        "day_low",
        "reference_price",
        "foreign_buy_volume",
        "foreign_sell_volume",
        "bid_1_price",
        "offer_1_price",
    ]
    lines = [f"{field}: {row.get(field, '')}" for field in fields if row.get(field)]
    return "\n".join(lines)


def build_technical_context(ticker: str | None) -> str:
    if not ticker:
        return ""

    ticker = ticker.upper()
    rows = load_ohlcv_rows(ticker)
    snapshot = latest_snapshot_context(ticker)
    lines = [f"Technical analysis data for {ticker}:"]

    if snapshot:
        lines.append("Current intraday snapshot:")
        lines.append(snapshot)

    if not rows:
        lines.append(
            "No historical OHLCV file with date/open/high/low/close/volume columns was found. "
            "RSI, MACD, moving averages and Bollinger Bands cannot be computed reliably from the current raw data."
        )
        lines.append(
            "The crawled 24HMoney technical page appears to expose only locked/summary content, "
            "not concrete indicator values."
        )
        return "\n".join(lines)

    closes = [row.close for row in rows]
    latest = rows[-1]
    lines.append(f"Latest OHLCV: {latest}")
    for window in [20, 50, 200]:
        value = simple_moving_average(closes, window)
        if value is not None:
            lines.append(f"SMA{window}: {value:.2f}")
    rsi14 = rsi(closes)
    if rsi14 is not None:
        lines.append(f"RSI14: {rsi14:.2f}")
    macd_values = macd(closes)
    if macd_values is not None:
        macd_line, signal_line, histogram = macd_values
        lines.append(
            f"MACD: line={macd_line:.2f}, signal={signal_line:.2f}, histogram={histogram:.2f}"
        )
    bands = bollinger(closes)
    if bands is not None:
        lower, middle, upper = bands
        lines.append(f"Bollinger(20,2): lower={lower:.2f}, middle={middle:.2f}, upper={upper:.2f}")
    return "\n".join(lines)
