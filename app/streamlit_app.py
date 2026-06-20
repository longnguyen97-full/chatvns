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
from app.market_snapshot import load_latest_market_snapshot
from app.ui import (
    freshness_label,
    inject_app_css,
    mascot_path,
    render_disclaimer,
    render_hero,
    render_trust_note,
    render_welcome,
)

try:
    from app.ui import apply_metric_card_style, render_section_header
except ImportError:
    def apply_metric_card_style() -> None:
        pass

    def render_section_header(label: str, description: str = "") -> None:
        st.subheader(label, divider="blue")
        if description:
            st.caption(description)


st.set_page_config(page_title="ChatVNS", page_icon=str(mascot_path("chatvns")), layout="wide")
inject_app_css()
apply_metric_card_style()

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
    with st.expander("Nguồn tham khảo", expanded=False):
        render_trust_note()
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
                st.info("Chưa có ảnh biểu đồ cho mã này.")

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
                st.info("Chưa có bảng CSV cho mã này.")

        with tab_pdfs:
            if pdfs:
                for index, pdf in enumerate(pdfs):
                    st.write(f"- {artifact_label(pdf)}: `{pdf.relative_to(PROJECT_ROOT).as_posix()}`")
                    st.download_button(
                        "Tải báo cáo PDF",
                        data=pdf.read_bytes(),
                        file_name=pdf.name,
                        mime="application/pdf",
                        key=f"{key_prefix}_pdf_{index}_{pdf.name}",
                    )
            else:
                st.info("Chưa có PDF cho mã này.")


ensure_state()

with st.sidebar:
    st.image(str(mascot_path("chatvns")), width=118)
    st.title("ChatVNS")
    st.caption("Trợ lý chứng khoán Việt Nam")
    st.link_button("💬 Trợ lý phân tích", "/", use_container_width=True)
    st.link_button("📊 Bảng điều khiển", "/1_Dashboard", use_container_width=True)
    st.divider()

    if st.button("Xóa hội thoại", use_container_width=True, icon="🧹"):
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


ticker_options = sorted(available_tickers())
render_hero(len(ticker_options), DEFAULT_TOP_K)

if not st.session_state.messages:
    render_welcome()
    starter_questions = [
        "Tóm tắt nhanh cổ phiếu HPG hiện tại",
        "FPT có những động lực tăng trưởng nào?",
        "Phân tích kỹ thuật VCB với dữ liệu hiện có",
    ]
    starter_cols = st.columns(3)
    for starter_index, (column, question) in enumerate(zip(starter_cols, starter_questions)):
        if column.button(question, key=f"starter_{starter_index}", use_container_width=True):
            st.session_state.pending_prompt = question
            st.rerun()

for message_index, message in enumerate(st.session_state.messages):
    avatar = str(mascot_path("chat")) if message["role"] == "assistant" else "👤"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        if message.get("sources"):
            render_sources(message["sources"])
        if message.get("ticker"):
            render_multimodal(message["ticker"], key_prefix=f"history_{message_index}")
        elif message.get("tickers"):
            for ticker in message["tickers"]:
                render_multimodal(ticker, key_prefix=f"history_{message_index}_{ticker}")

typed_prompt = st.chat_input(
    "Hỏi về một mã cổ phiếu, báo cáo hoặc chỉ báo kỹ thuật...",
    key="chat_question",
)
prompt = st.session_state.pending_prompt or typed_prompt
st.session_state.pending_prompt = None

if prompt:
    detected_tickers = infer_tickers(prompt)
    detected_ticker = detected_tickers[0] if len(detected_tickers) == 1 else None
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=str(mascot_path("chat"))):
        with st.status("Đang tìm dữ liệu và kiểm tra nguồn...", expanded=True) as status:
            progress_col, mascot_col = st.columns([4, 1])
            progress_col.write("Truy xuất kết hợp → xếp hạng lại → tạo câu trả lời")
            mascot_col.image(str(mascot_path("processing")), width=72)
            started_at = time.perf_counter()
            result = answer_question(prompt, ticker=detected_ticker, top_k=DEFAULT_TOP_K)
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            status.update(label=f"Đã hoàn tất trong {latency_ms / 1000:.1f}s", state="complete", expanded=False)

        answer = result["answer"]
        st.write_stream(stream_text(answer))

        if detected_ticker:
            snapshot = load_latest_market_snapshot(detected_ticker)
            if snapshot:
                updated_at = snapshot.row.get("crawled_at_utc") or snapshot.row.get("updated_at")
                label, css_class = freshness_label(updated_at)
                st.markdown(f'<span class="{css_class}">&#9679; {label}</span>', unsafe_allow_html=True)

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
    st.rerun()


render_disclaimer()
