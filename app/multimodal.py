from __future__ import annotations

from pathlib import Path

from app.config import RAW_DIR


def latest_file(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def latest_chart_image(ticker: str | None) -> Path | None:
    if not ticker:
        return None
    image_dir = RAW_DIR / "images" / ticker.upper()
    if not image_dir.exists():
        return None
    candidates = [
        path
        for path in image_dir.glob("*")
        if path.is_file()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        and ("chart" in path.stem.lower() or "tradingview" in path.stem.lower())
    ]
    return latest_file(candidates)


def ticker_tables(ticker: str | None, limit: int = 5) -> list[Path]:
    if not ticker:
        return []
    csv_dir = RAW_DIR / "csv" / ticker.upper()
    if not csv_dir.exists():
        return []
    candidates = [
        path
        for path in csv_dir.glob("*.csv")
        if path.is_file() and has_meaningful_csv_content(path)
    ]
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def has_meaningful_csv_content(path: Path) -> bool:
    try:
        rows = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    except OSError:
        return False
    non_empty_rows = [row for row in rows if row.strip()]
    if len(non_empty_rows) < 2:
        return False
    return any(row.count(",") >= 2 for row in non_empty_rows[:3])


def artifact_label(path: Path) -> str:
    stem = path.stem.lower()
    if "stock_overview_timeseries" in stem:
        return "Bảng giá và giao dịch"
    if "financial_document" in stem or "financial_documents" in stem:
        return "Báo cáo tài chính"
    if "analysis_report" in stem:
        return "Báo cáo phân tích"
    if "ticker_news" in stem or "news_events" in stem:
        return "Tin tức và sự kiện"
    if "chart" in stem or "tradingview" in stem:
        return "Biểu đồ TradingView"
    return path.name


def ticker_pdfs(ticker: str | None, limit: int = 5) -> list[Path]:
    if not ticker:
        return []
    pdf_dir = RAW_DIR / "pdf" / ticker.upper()
    if not pdf_dir.exists():
        return []
    candidates = [path for path in pdf_dir.glob("*.pdf") if path.is_file()]
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def multimodal_artifacts(ticker: str | None) -> dict[str, object]:
    return {
        "chart": latest_chart_image(ticker),
        "tables": ticker_tables(ticker),
        "pdfs": ticker_pdfs(ticker),
    }
