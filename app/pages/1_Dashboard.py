from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DATA_DIR, PROCESSED_DIR, RAW_DIR
from app.evaluate import EVAL_CASES_PATH, EVAL_REPORT_DIR
from app.observability import INTERACTION_LOG_PATH, load_interaction_logs


st.set_page_config(page_title="ChatVNS Dashboard", page_icon=":bar_chart:", layout="wide")


def count_files(root: Path, pattern: str = "*") -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob(pattern) if path.is_file())


def count_jsonl_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="ignore") as file:
        return sum(1 for line in file if line.strip())


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def latest_file(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    files = [path for path in root.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def format_time(path: Path | None) -> str:
    if not path or not path.exists():
        return "N/A"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def available_tickers() -> list[str]:
    tickers: set[str] = set()
    for category in ["html", "text", "csv", "pdf", "images", "metadata"]:
        root = RAW_DIR / category
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.is_dir() and path.name.lower() != "market":
                tickers.add(path.name.upper())
    return sorted(tickers)


def raw_inventory_frame() -> pd.DataFrame:
    rows = []
    categories = ["html", "text", "csv", "pdf", "images", "metadata"]
    for ticker in available_tickers():
        row = {"ticker": ticker}
        for category in categories:
            row[category] = count_files(RAW_DIR / category / ticker)
        row["chunks"] = count_jsonl_lines(PROCESSED_DIR / "chunks" / ticker / "chunks.jsonl")
        rows.append(row)

    market_chunks = count_jsonl_lines(PROCESSED_DIR / "chunks" / "market" / "chunks.jsonl")
    if not market_chunks:
        market_chunks = count_jsonl_lines(PROCESSED_DIR / "chunks" / "MARKET" / "chunks.jsonl")
    if market_chunks or count_files(RAW_DIR / "text" / "market"):
        rows.append(
            {
                "ticker": "",
                "scope": "market",
                "html": count_files(RAW_DIR / "html" / "market"),
                "text": count_files(RAW_DIR / "text" / "market"),
                "csv": count_files(RAW_DIR / "csv" / "market"),
                "pdf": count_files(RAW_DIR / "pdf" / "market"),
                "images": count_files(RAW_DIR / "images" / "market"),
                "metadata": count_files(RAW_DIR / "metadata" / "market"),
                "chunks": market_chunks,
            }
        )

    return pd.DataFrame(rows)


def latest_evaluation_report() -> tuple[Path | None, dict | None]:
    if not EVAL_REPORT_DIR.exists():
        return None, None

    files = sorted(EVAL_REPORT_DIR.glob("evaluation_report_*.json"), key=lambda item: item.stat().st_mtime)
    for path in reversed(files):
        payload = load_json(path)
        if isinstance(payload, dict):
            return path, payload
    return None, None


def eval_case_count() -> int:
    payload = load_json(EVAL_CASES_PATH)
    if isinstance(payload, dict):
        cases = payload.get("cases", [])
    elif isinstance(payload, list):
        cases = payload
    else:
        cases = []
    return len([case for case in cases if isinstance(case, dict)])


def run_summary() -> dict | None:
    path = latest_file(DATA_DIR / "logs" / "crawl_logs", "run_summary_*.json")
    payload = load_json(path) if path else None
    if isinstance(payload, dict):
        payload["_path"] = path
        return payload
    return None


def recent_processed_files(limit: int = 12) -> pd.DataFrame:
    root = PROCESSED_DIR / "text"
    if not root.exists():
        return pd.DataFrame()

    files = sorted(
        [path for path in root.rglob("*.txt") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    return pd.DataFrame(
        [
            {
                "scope": path.parent.name.upper(),
                "file": path.name,
                "updated": format_time(path),
                "size_kb": round(path.stat().st_size / 1024, 1),
            }
            for path in files
        ]
    )


def metric_value(summary: dict | None, *keys: str, default: str = "N/A") -> str | float:
    value = summary
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def interaction_frame(limit: int = 100) -> pd.DataFrame:
    rows = load_interaction_logs(limit=limit)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    expected_columns = [
        "timestamp_utc",
        "ticker",
        "question",
        "latency_ms",
        "source_count",
        "answer_chars",
        "top_k",
    ]
    for column in expected_columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[expected_columns].sort_values("timestamp_utc", ascending=False)


def mean_value(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return 0.0
    return round(float(values.mean()), 2)


def render_report_header(path: Path | None, report: dict, label: str) -> None:
    if path:
        st.caption(f"{label}: `{path.relative_to(PROJECT_ROOT).as_posix()}`")
    st.caption(f"Updated: {format_time(path)}")
    st.caption(f"Top-k: `{report.get('top_k', 'N/A')}` | Cases: `{report.get('case_count', 'N/A')}`")


def render_evaluation_report(path: Path | None, report: dict | None) -> None:
    if not report:
        st.info("Chưa có evaluation report. Chạy `python -m app.evaluate` để tạo report đầy đủ.")
        return

    retrieval = report.get("retrieval", {}).get("summary", {})
    generation = report.get("generation", {}).get("summary", {})
    performance = report.get("performance", {})

    render_report_header(path, report, "Evaluation report")
    st.caption(f"DeepEval model: `{report.get('eval_model') or 'N/A'}`")

    st.write("Retrieval")
    r1, r2 = st.columns(2)
    r1.metric("Recall@5", metric_value(retrieval, "recall_at_k"))
    r2.metric("MRR", metric_value(retrieval, "mean_mrr"))

    st.write("Generation")
    g1, g2 = st.columns(2)
    g1.metric("Faithfulness", metric_value(generation, "faithfulness"))
    g2.metric("Answer relevancy", metric_value(generation, "answer_relevancy"))

    st.write("Finance")
    f1, f2 = st.columns(2)
    f1.metric("Numerical accuracy", metric_value(generation, "numerical_accuracy"))
    f2.metric("Citation accuracy", metric_value(generation, "citation_accuracy"))

    st.write("Performance")
    p1, p2 = st.columns(2)
    p1.metric("Retrieval p95 ms", metric_value(performance, "retrieval_latency_ms", "p95_ms"))
    p2.metric("Answer p95 ms", metric_value(performance, "generation_latency_ms", "p95_ms"))

    retrieval_cases = report.get("retrieval", {}).get("cases", [])
    if retrieval_cases:
        st.write("Retrieval cases")
        case_frame = pd.DataFrame(retrieval_cases)
        columns = ["case_id", "ticker", "mrr", "recall_at_k"]
        available_columns = [column for column in columns if column in case_frame.columns]
        st.dataframe(case_frame[available_columns], use_container_width=True, hide_index=True)

    generation_cases = report.get("generation", {}).get("cases", [])
    if generation_cases:
        st.write("Generation cases")
        case_frame = pd.DataFrame(generation_cases)
        columns = ["case_id", "ticker", "faithfulness", "answer_relevancy", "numerical_accuracy", "citation_accuracy"]
        available_columns = [column for column in columns if column in case_frame.columns]
        st.dataframe(case_frame[available_columns], use_container_width=True, hide_index=True)


st.title("Dashboard")
st.caption("Giám sát dữ liệu, coverage RAG, evaluation và trạng thái artifact của ChatVNS.")

st.page_link("streamlit_app.py", label="Mở Chatbot")

inventory = raw_inventory_frame()
evaluation_path, evaluation_report = latest_evaluation_report()
summary = run_summary()
interactions = interaction_frame()

total_chunks = int(inventory["chunks"].sum()) if not inventory.empty else 0
total_raw_files = sum(count_files(RAW_DIR / category) for category in ["html", "text", "csv", "pdf", "images"])

col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("Tickers", len([ticker for ticker in available_tickers()]))
col_b.metric("Raw artifacts", total_raw_files)
col_c.metric("Indexed chunks", total_chunks)
col_d.metric("Eval cases", eval_case_count())
col_e.metric("Logged chats", 0 if interactions.empty else len(interactions))

st.divider()

left, right = st.columns([1.15, 0.85])

with left:
    st.subheader("Data inventory")
    if inventory.empty:
        st.info("Chưa tìm thấy dữ liệu raw/processed.")
    else:
        st.dataframe(inventory, use_container_width=True, hide_index=True)

    st.subheader("Recent processed text")
    recent_files = recent_processed_files()
    if recent_files.empty:
        st.info("Chưa có text đã xử lý.")
    else:
        st.dataframe(recent_files, use_container_width=True, hide_index=True)

    st.subheader("Chatbot logs")
    if interactions.empty:
        st.info("Chua co interaction log. Hay hoi chatbot mot cau de dashboard bat dau co du lieu.")
    else:
        l1, l2, l3 = st.columns(3)
        l1.metric("Avg latency ms", mean_value(interactions, "latency_ms"))
        l2.metric("Avg sources", mean_value(interactions, "source_count"))
        l3.metric("Avg answer chars", mean_value(interactions, "answer_chars"))
        st.caption(f"Source: `{INTERACTION_LOG_PATH.relative_to(PROJECT_ROOT).as_posix()}`")
        st.dataframe(interactions.head(25), use_container_width=True, hide_index=True)

with right:
    st.subheader("Evaluation")
    render_evaluation_report(evaluation_path, evaluation_report)

    st.subheader("Latest crawl")
    if not summary:
        st.info("Chưa có crawl summary.")
    else:
        summary_path = summary.get("_path")
        st.caption(f"Source: `{summary_path.relative_to(PROJECT_ROOT).as_posix()}`")
        display_summary = {key: value for key, value in summary.items() if key != "_path"}
        st.json(display_summary, expanded=False)
