from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

from celery_app import app
from crawl_raw_data import DEFAULT_TICKERS, run_collector


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def ensure_qdrant() -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "qdrant"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def run_index_pipeline() -> dict:
    from app.processing import process_raw_data_with_summary
    from app.qa_suggestions import export_suggested_questions_json
    from app.vector_store import index_chunks

    ensure_qdrant()
    suggestions = export_suggested_questions_json()
    chunks, summary = process_raw_data_with_summary()

    def on_index_progress(event: dict) -> None:
        if event["stage"] != "embedding":
            return
        print(
            "Indexing "
            f"batch {event['batch_number']}/{event['total_batches']} "
            f"chunks={event['batch_size']} "
            f"cache_hits={event.get('cache_hits', 0)} "
            f"api_chunks={event.get('cache_misses', 0)}"
        )

    indexed_count = index_chunks(chunks, progress_callback=on_index_progress)
    return {
        "suggestion_group_count": len(suggestions),
        "chunk_count": len(chunks),
        "indexed_count": indexed_count,
        "summary": summary,
    }


@app.task(name="tasks.index_processed_data")
def index_processed_data() -> dict:
    return run_index_pipeline()


def crawl_then_index(
    tickers: Iterable[str],
    include_news: bool = False,
    include_charts: bool = False,
    max_reports: int = 5,
    delay_seconds: float = 1.5,
    timeout: int = 30,
) -> dict:
    crawl_result = run_collector(
        tickers=tickers,
        include_news=include_news,
        include_charts=include_charts,
        max_reports=max_reports,
        delay_seconds=delay_seconds,
        timeout=timeout,
    )
    index_result = run_index_pipeline()
    return {
        "crawl": crawl_result,
        "index": index_result,
    }


@app.task(name="tasks.crawl_tickers")
def crawl_tickers(
    tickers: list[str],
    include_news: bool = False,
    include_charts: bool = False,
    max_reports: int = 5,
    delay_seconds: float = 1.5,
    timeout: int = 30,
) -> dict:
    return run_collector(
        tickers=tickers,
        include_news=include_news,
        include_charts=include_charts,
        max_reports=max_reports,
        delay_seconds=delay_seconds,
        timeout=timeout,
    )


@app.task(name="tasks.crawl_tickers_and_index")
def crawl_tickers_and_index(
    tickers: list[str],
    include_news: bool = False,
    include_charts: bool = False,
    max_reports: int = 5,
    delay_seconds: float = 1.5,
    timeout: int = 30,
) -> dict:
    return crawl_then_index(
        tickers=tickers,
        include_news=include_news,
        include_charts=include_charts,
        max_reports=max_reports,
        delay_seconds=delay_seconds,
        timeout=timeout,
    )


@app.task(name="tasks.crawl_default_tickers")
def crawl_default_tickers() -> dict:
    return run_collector(
        tickers=list(DEFAULT_TICKERS),
        include_news=False,
        include_charts=False,
    )


@app.task(name="tasks.crawl_default_tickers_and_index")
def crawl_default_tickers_and_index() -> dict:
    return crawl_then_index(
        tickers=list(DEFAULT_TICKERS),
        include_news=False,
        include_charts=False,
    )


@app.task(name="tasks.crawl_market_news")
def crawl_market_news(tickers: Iterable[str] | None = None) -> dict:
    return run_collector(
        tickers=list(tickers or DEFAULT_TICKERS),
        include_news=True,
        include_charts=False,
        max_reports=0,
    )


@app.task(name="tasks.crawl_market_news_and_index")
def crawl_market_news_and_index(tickers: Iterable[str] | None = None) -> dict:
    return crawl_then_index(
        tickers=list(tickers or DEFAULT_TICKERS),
        include_news=True,
        include_charts=False,
        max_reports=0,
    )
