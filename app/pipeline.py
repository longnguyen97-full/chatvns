from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from app.processing import process_raw_data_with_summary
from app.qa_suggestions import export_suggested_questions_json
from app.vector_store import index_chunks


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PipelineConsole:
    def __init__(self) -> None:
        self._started_at = time.perf_counter()

    def intro(self, command: str) -> None:
        print("=" * 72)
        print("ChatVNS pipeline")
        print(f"Command: {command}")
        print("Flow: collect raw data -> process/chunk -> embed/index Qdrant -> Streamlit")
        print("=" * 72)

    def stage(self, number: int, total: int, title: str, detail: str | None = None) -> float:
        print()
        print(f"[{number}/{total}] {title}")
        if detail:
            print(f"      {detail}")
        return time.perf_counter()

    def done(self, started_at: float, detail: str | None = None) -> None:
        duration = time.perf_counter() - started_at
        suffix = f" | {detail}" if detail else ""
        print(f"      DONE in {duration:.1f}s{suffix}")

    def note(self, message: str) -> None:
        print(f"      {message}")

    def finish(self) -> None:
        total = time.perf_counter() - self._started_at
        print()
        print(f"Pipeline ready in {total:.1f}s")


def format_counts(values: dict[str, int]) -> str:
    if not values:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in values.items())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ChatVNS pipeline commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect raw data into data/raw.")
    add_collect_args(collect)

    index = subparsers.add_parser("index", help="Process raw data and index chunks into Qdrant.")
    index.add_argument("--skip-qdrant", action="store_true")

    chat = subparsers.add_parser("chat", help="Open the Streamlit chatbot.")
    chat.add_argument("--server-port", default="8501")

    all_cmd = subparsers.add_parser("all", help="Collect, index, then open Streamlit.")
    add_collect_args(all_cmd)
    all_cmd.add_argument("--server-port", default="8501")
    all_cmd.add_argument("--skip-qdrant", action="store_true")
    return parser.parse_args()


def add_collect_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tickers", nargs="+", default=["HPG", "FPT", "VCB"])
    parser.add_argument("--include-news", action="store_true")
    parser.add_argument("--include-charts", action="store_true")
    parser.add_argument("--max-reports", type=int, default=5)
    parser.add_argument("--delay-seconds", type=float, default=1.5)
    parser.add_argument("--timeout", type=int, default=30)


def run_collect(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "bot-collect-data" / "crawl_raw_data.py"),
        "--tickers",
        *args.tickers,
        "--max-reports",
        str(args.max_reports),
        "--delay-seconds",
        str(args.delay_seconds),
        "--timeout",
        str(args.timeout),
    ]
    if args.include_news:
        command.append("--include-news")
    if args.include_charts:
        command.append("--include-charts")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def ensure_qdrant() -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "qdrant"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def run_index() -> None:
    suggestions = export_suggested_questions_json()
    print(f"      Synced Q&A suggestions: groups={len(suggestions)}")
    chunks, summary = process_raw_data_with_summary()
    print(
        "      Processed raw data: "
        f"documents={summary['document_count']}, "
        f"chunks={summary['chunk_count']}, "
        f"tickers={', '.join(summary['tickers']) or 'none'}"
    )
    print(f"      Modalities: {format_counts(summary['modalities'])}")
    print(f"      Chunks by ticker: {format_counts(summary['chunks_by_ticker'])}")
    print(f"      Chunks by scope: {format_counts(summary['chunks_by_scope'])}")
    print(f"      Structures: {format_counts(summary['structures'])}")

    def on_index_progress(event: dict) -> None:
        action = "Embedding" if event["stage"] == "embedding" else "Upserted"
        cache_detail = ""
        if event["stage"] == "embedding" and "cache_hits" in event:
            cache_detail = f", cache_hits={event['cache_hits']}, api_chunks={event['cache_misses']}"
        print(
            "      "
            f"{action} batch {event['batch_number']}/{event['total_batches']} "
            f"({event['batch_size']} chunks, indexed={event['indexed_so_far']}/{event['total_chunks']}"
            f"{cache_detail})"
        )

    indexed_count = index_chunks(chunks, progress_callback=on_index_progress)
    print(
        json.dumps(
            {
                "chunk_count": len(chunks),
                "indexed_count": indexed_count,
                "documents_by_ticker": summary["documents_by_ticker"],
                "chunks_by_ticker": summary["chunks_by_ticker"],
                "documents_by_scope": summary["documents_by_scope"],
                "chunks_by_scope": summary["chunks_by_scope"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_streamlit(server_port: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(PROJECT_ROOT / "app" / "streamlit_app.py"),
            "--server.port",
            server_port,
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )


def main() -> int:
    args = parse_args()
    console = PipelineConsole()
    console.intro(args.command)
    if args.command == "collect":
        stage = console.stage(
            1,
            1,
            "Collect raw data",
            f"tickers={', '.join(args.tickers)} | news={args.include_news} | charts={args.include_charts}",
        )
        run_collect(args)
        console.done(stage)
        console.finish()
        return 0
    if args.command == "index":
        if not args.skip_qdrant:
            stage = console.stage(1, 2, "Start Qdrant", "docker compose up -d qdrant")
            ensure_qdrant()
            console.done(stage)
        stage = console.stage(2 if not args.skip_qdrant else 1, 2 if not args.skip_qdrant else 1, "Process and index", "parse raw files -> chunk -> embed -> upsert")
        run_index()
        console.done(stage)
        console.finish()
        return 0
    if args.command == "chat":
        stage = console.stage(1, 1, "Open Streamlit", f"http://localhost:{args.server_port}")
        console.note("Launching Streamlit app. Keep this terminal open while using the UI.")
        console.done(stage, f"url=http://localhost:{args.server_port}")
        run_streamlit(args.server_port)
        return 0
    if args.command == "all":
        if not args.skip_qdrant:
            stage = console.stage(1, 4, "Start Qdrant", "docker compose up -d qdrant")
            ensure_qdrant()
            console.done(stage)
        collect_stage = console.stage(
            2 if not args.skip_qdrant else 1,
            4 if not args.skip_qdrant else 3,
            "Collect raw data",
            f"tickers={', '.join(args.tickers)} | news={args.include_news} | charts={args.include_charts}",
        )
        run_collect(args)
        console.done(collect_stage)
        index_stage = console.stage(
            3 if not args.skip_qdrant else 2,
            4 if not args.skip_qdrant else 3,
            "Process and index",
            "parse raw files -> chunk -> embed -> upsert",
        )
        run_index()
        console.done(index_stage)
        streamlit_stage = console.stage(
            4 if not args.skip_qdrant else 3,
            4 if not args.skip_qdrant else 3,
            "Open Streamlit",
            f"http://localhost:{args.server_port}",
        )
        console.note("Launching Streamlit app. Keep this terminal open while using the UI.")
        console.done(streamlit_stage, f"url=http://localhost:{args.server_port}")
        console.finish()
        run_streamlit(args.server_port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
