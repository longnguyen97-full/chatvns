from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DEFAULT_TOP_K, RAW_DIR
from app.multimodal import artifact_label, multimodal_artifacts
from app.observability import append_interaction_log
from app.qa_suggestions import load_suggested_questions
from app.rag import answer_question


st.set_page_config(page_title="ChatVNS RAG", page_icon=":chart_with_upwards_trend:", layout="wide")

TICKER_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")


def stream_text(text: str):
    for token in text.split(" "):
        yield token + " "
        time.sleep(0.01)


def ensure_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None


def available_tickers() -> set[str]:
    tickers: set[str] = set()
    for category in ["html", "text", "csv", "pdf", "images", "metadata"]:
        root = RAW_DIR / category
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.is_dir() and path.name.lower() != "market":
                tickers.add(path.name.upper())
    return tickers


def infer_ticker(question: str) -> str | None:
    tickers = infer_tickers(question)
    return tickers[0] if len(tickers) == 1 else None


def infer_tickers(question: str) -> list[str]:
    tickers = available_tickers()
    if not tickers:
        return []

    matches = []
    for match in TICKER_PATTERN.findall(question.upper()):
        if match in tickers:
            matches.append(match)
    return list(dict.fromkeys(matches))


def render_sources(sources: list[dict]) -> None:
    with st.expander("Sources"):
        seen: set[str] = set()
        for source in sources:
            url = source.get("url")
            artifact_path = source.get("artifact_path") or source.get("source_path")
            link_target = url or artifact_path
            if not link_target or link_target in seen:
                continue
            seen.add(link_target)
            label = source_label(source)
            if url:
                st.markdown(f"- [{label}]({url})")
            else:
                st.markdown(f"- {label}: `{artifact_path}`")


def source_label(source: dict) -> str:
    source_path = str(source.get("source_path") or source.get("artifact_path") or "")
    ticker = source.get("ticker") or source.get("scope") or "market"
    if source.get("structure_type") == "market_snapshot":
        return f"{ticker} - Bảng giá và giao dịch"
    if "analysis_report" in source_path:
        return f"{ticker} - Báo cáo phân tích"
    if "financial_document" in source_path or "financial_documents" in source_path:
        return f"{ticker} - Báo cáo tài chính"
    if "ticker_news" in source_path or "news_events" in source_path:
        return f"{ticker} - Tin tức và sự kiện"
    if "stock_overview" in source_path:
        return f"{ticker} - Trang tổng quan cổ phiếu"
    if "world_market" in source_path:
        return "Thị trường thế giới"
    return f"{ticker} - Nguồn dữ liệu"


def render_multimodal(ticker: str | None, key_prefix: str) -> None:
    if not ticker:
        return

    artifacts = multimodal_artifacts(ticker)
    chart = artifacts["chart"]
    tables = artifacts["tables"]
    pdfs = artifacts["pdfs"]

    if not chart and not tables and not pdfs:
        return

    with st.expander("Dữ liệu liên quan", expanded=True):
        tab_chart, tab_tables, tab_pdfs = st.tabs(
            ["Biểu đồ giá", "Bảng giá / dữ liệu", "Báo cáo PDF"]
        )
        with tab_chart:
            if chart:
                st.image(str(chart), caption=artifact_label(chart), use_container_width=True)
            else:
                st.info("Chưa có ảnh chart cho mã này.")

        with tab_tables:
            if tables:
                table_options = [str(path.relative_to(PROJECT_ROOT)) for path in tables]
                selected_table = st.selectbox(
                    "Chọn bảng dữ liệu",
                    options=table_options,
                    format_func=lambda value: f"{artifact_label(PROJECT_ROOT / value)} - {Path(value).name}",
                    key=f"{key_prefix}_table_{ticker}",
                )
                table_path = PROJECT_ROOT / selected_table
                try:
                    st.dataframe(pd.read_csv(table_path), use_container_width=True)
                except Exception:
                    st.code(table_path.read_text(encoding="utf-8-sig", errors="ignore")[:5000])
            else:
                st.info("Chưa có CSV table cho mã này.")

        with tab_pdfs:
            if pdfs:
                for index, pdf in enumerate(pdfs):
                    st.write(f"- {artifact_label(pdf)}: `{pdf.relative_to(PROJECT_ROOT).as_posix()}`")
                    st.download_button(
                        "Download PDF",
                        data=pdf.read_bytes(),
                        file_name=pdf.name,
                        mime="application/pdf",
                        key=f"{key_prefix}_pdf_{index}_{pdf.name}",
                    )
            else:
                st.info("Chưa có PDF cho mã này.")


ensure_state()

with st.sidebar:
    st.title("ChatVNS")
    st.caption("Multimodal RAG Stock VN")

    # st.page_link("streamlit_app.py", label="Chatbot")
    # st.page_link("pages/1_Dashboard.py", label="Dashboard")
    # st.divider()

    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    suggestions = load_suggested_questions()
    if suggestions:
        st.divider()
        st.write("Gợi ý câu hỏi")
        for group_index, group in enumerate(suggestions):
            with st.expander(group["category"], expanded=group_index == 0):
                for question_index, question in enumerate(group["questions"]):
                    if st.button(
                        question,
                        key=f"suggested_question_{group_index}_{question_index}",
                        use_container_width=True,
                    ):
                        st.session_state.pending_prompt = question
                        st.rerun()


st.title("ChatVNS")
st.caption("Hỏi đáp trên dữ liệu cổ phiếu đã crawl, xử lý và index.")

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            render_sources(message["sources"])
        if message.get("ticker"):
            render_multimodal(message["ticker"], key_prefix=f"history_{message_index}")
        elif message.get("tickers"):
            for ticker in message["tickers"]:
                render_multimodal(ticker, key_prefix=f"history_{message_index}_{ticker}")

prompt = st.session_state.pending_prompt or st.chat_input("Nhập câu hỏi về cổ phiếu...")
st.session_state.pending_prompt = None

if prompt:
    detected_tickers = infer_tickers(prompt)
    detected_ticker = detected_tickers[0] if len(detected_tickers) == 1 else None
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving context..."):
            started_at = time.perf_counter()
            result = answer_question(prompt, ticker=detected_ticker, top_k=DEFAULT_TOP_K)
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

        answer = result["answer"]
        st.write_stream(stream_text(answer))

        sources = result.get("sources", [])
        if sources:
            render_sources(sources)
        for ticker in detected_tickers:
            render_multimodal(ticker, key_prefix=f"current_{len(st.session_state.messages)}_{ticker}")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "ticker": detected_ticker,
            "tickers": detected_tickers,
            "latency_ms": latency_ms,
        }
    )

    append_interaction_log(
        {
            "question": prompt,
            "ticker": detected_ticker,
            "tickers": detected_tickers,
            "top_k": DEFAULT_TOP_K,
            "latency_ms": latency_ms,
            "source_count": len(sources),
            "answer_chars": len(answer),
            "source_paths": [
                source.get("artifact_path") or source.get("source_path")
                for source in sources[:5]
                if source.get("artifact_path") or source.get("source_path")
            ],
        }
    )
