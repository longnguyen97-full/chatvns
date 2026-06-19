from __future__ import annotations

import re

from app.config import DEFAULT_TOP_K, GEMINI_API_KEY, GEMINI_MODEL, RAW_DIR
from app.context_compression import compress_chunk_text
from app.intermarket import build_intermarket_context
from app.market_snapshot import (
    build_market_snapshot_context,
    compressed_quick_summary_context,
    format_market_snapshot_answer,
    format_quick_stock_summary,
    is_market_snapshot_query,
    is_quick_summary_query,
    load_latest_market_snapshot,
)
from app.prompts import load_prompt
from app.retriever import hybrid_retrieve
from app.schemas import RetrievedChunk
from app.technical_analysis import build_technical_context, is_technical_query


SYSTEM_PROMPT = load_prompt("rag_system.md")


def build_context(chunks: list[RetrievedChunk], question: str = "") -> str:
    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        blocks.append(
            "\n".join(
                [
                    (
                        f"[{index}] ticker={chunk.ticker} modality={chunk.modality} "
                        f"scope={chunk.scope or chunk.ticker} structure={chunk.structure_type} score={chunk.score:.4f}"
                    ),
                    f"source={chunk.source_path}",
                    f"heading={' > '.join(chunk.heading_path)}",
                    compress_chunk_text(question, chunk),
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def build_prompt(question: str, chunks: list[RetrievedChunk], extra_context: str = "") -> str:
    context_parts = []
    if extra_context:
        context_parts.extend(["Additional structured context:", extra_context])
    context_parts.extend(["Retrieved context:", build_context(chunks, question)])
    return "\n\n".join(
        [
            SYSTEM_PROMPT,
            *context_parts,
            f"User question: {question}",
            "Answer:",
        ]
    )


def generate_answer(question: str, chunks: list[RetrievedChunk], extra_context: str = "") -> str:
    if not chunks and not extra_context:
        return "Chưa tìm thấy context phù hợp trong vector DB. Hãy index `data/raw` trước."

    prompt = build_prompt(question, chunks, extra_context)
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)
            response = model.generate_content(prompt)
            return response.text or ""
        except Exception as exc:
            return (
                f"Không gọi được Gemini ({exc}). Context liên quan:\n\n"
                f"{extra_context}\n\n{build_context(chunks, question)}"
            )

    return (
        "Chưa cấu hình `GEMINI_API_KEY` nên trả về context liên quan nhất:\n\n"
        f"{extra_context}\n\n{build_context(chunks, question)}"
    )


def generate_quick_summary(
    question: str,
    snapshot,
    chunks: list[RetrievedChunk],
    ticker: str,
) -> str:
    fallback = format_quick_stock_summary(snapshot, chunks, ticker=ticker)
    if not GEMINI_API_KEY:
        return fallback

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        prompt = load_prompt("quick_summary.md").format(
            ticker=ticker.upper(),
            question=question,
            compressed_context=compressed_quick_summary_context(snapshot, chunks),
        )
        response = model.generate_content(prompt)
        answer = (response.text or "").strip()
        return answer or fallback
    except Exception:
        return fallback


def chunk_source(chunk: RetrievedChunk) -> dict:
    return {
        "score": chunk.score,
        "ticker": chunk.ticker,
        "scope": chunk.scope,
        "modality": chunk.modality,
        "structure_type": chunk.structure_type,
        "heading_path": chunk.heading_path,
        "source_path": chunk.source_path,
        "url": chunk.metadata.get("url"),
        "artifact_path": chunk.metadata.get("artifact_path"),
    }


def friendly_source_label(source: dict) -> str:
    source_path = str(source.get("source_path") or source.get("artifact_path") or "").lower()
    ticker = str(source.get("ticker") or source.get("scope") or "thị trường").upper()
    if source.get("structure_type") == "market_snapshot":
        return f"Bảng giá {ticker}"
    if "analysis_report" in source_path:
        return f"Báo cáo phân tích {ticker}"
    if "financial_document" in source_path or "financial_documents" in source_path:
        return f"Báo cáo tài chính {ticker}"
    if "ticker_news" in source_path or "news_events" in source_path:
        return f"Tin tức và sự kiện {ticker}"
    if "stock_overview" in source_path:
        return f"Tổng quan cổ phiếu {ticker}"
    if "world_market" in source_path:
        return "Thị trường thế giới"
    return f"Nguồn dữ liệu {ticker}"


def format_answer_citations(answer: str, sources: list[dict]) -> str:
    formatted = str(answer)
    replacements: dict[str, str] = {}
    for source in sources:
        label = friendly_source_label(source)
        url = str(source.get("url") or "").strip()
        replacement = f"[{label}]({url})" if url else f"**{label}**"
        for value in [source.get("source_path"), source.get("artifact_path")]:
            path = str(value or "").strip().replace("\\", "/")
            if not path:
                continue
            variants = {path}
            if path.startswith("data/"):
                variants.add(path.removeprefix("data/"))
            else:
                variants.add(f"data/{path}")
            replacements.update({variant: replacement for variant in variants})

    for path in sorted(replacements, key=len, reverse=True):
        replacement = replacements[path]
        escaped = re.escape(path)
        formatted = re.sub(rf"`{escaped}`", replacement, formatted)
        formatted = re.sub(rf"\({escaped}\)", replacement, formatted)
        formatted = re.sub(escaped, replacement, formatted)
    return formatted


def answer_question(question: str, ticker: str | None = None, top_k: int = DEFAULT_TOP_K) -> dict:
    chunks = hybrid_retrieve(question, top_k=top_k, ticker=ticker)
    extra_context_parts: list[str] = []
    sources = [chunk_source(chunk) for chunk in chunks]
    quick_summary_query = is_quick_summary_query(question)

    intermarket_context, intermarket_source = build_intermarket_context(question)
    if intermarket_context and not ticker:
        extra_context_parts.append(intermarket_context)
        if intermarket_source:
            sources.insert(0, intermarket_source)

    snapshot = load_latest_market_snapshot(ticker) if (is_market_snapshot_query(question) or quick_summary_query) else None
    snapshot_context = build_market_snapshot_context(snapshot)
    if snapshot_context and snapshot:
        extra_context_parts.append(snapshot_context)
        sources.insert(
            0,
            {
                "score": 1.0,
                "ticker": snapshot.ticker,
                "modality": "table",
                "structure_type": "market_snapshot",
                "heading_path": [],
                "source_path": snapshot.path.relative_to(RAW_DIR.parent).as_posix(),
                "url": f"https://24hmoney.vn/stock/{snapshot.ticker}",
                "artifact_path": snapshot.path.relative_to(RAW_DIR.parent).as_posix(),
            },
        )

    if is_technical_query(question):
        technical_context = build_technical_context(ticker)
        if technical_context:
            extra_context_parts.append(technical_context)

    extra_context = "\n\n---\n\n".join(extra_context_parts)
    if quick_summary_query and ticker:
        answer = generate_quick_summary(question, snapshot, chunks, ticker=ticker)
    elif snapshot and snapshot_context:
        answer = format_market_snapshot_answer(snapshot)
    else:
        answer = generate_answer(question, chunks, extra_context)
    answer = format_answer_citations(answer, sources)
    return {
        "question": question,
        "ticker": ticker,
        "answer": answer,
        "sources": sources,
    }
