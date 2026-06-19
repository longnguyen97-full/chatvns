from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

try:
    from streamlit_extras.metric_cards import style_metric_cards
except ImportError:
    style_metric_cards = None

from app.config import PROJECT_ROOT


MASCOT_DIR = PROJECT_ROOT / "assets" / "mascots"


def mascot_path(name: str) -> Path:
    path = MASCOT_DIR / f"{name}.png"
    return path if path.exists() else MASCOT_DIR / "chatvns.png"


def mascot_data_uri(name: str) -> str:
    path = mascot_path(name)
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def inject_app_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --chatvns-blue: #0877e8;
            --chatvns-deep: #073b74;
            --chatvns-cyan: #19b9f2;
            --chatvns-ink: #10243e;
            --chatvns-soft: #eef7ff;
        }
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 82% 4%, rgba(25,185,242,.13), transparent 24rem),
                radial-gradient(circle at 12% 18%, rgba(8,119,232,.09), transparent 28rem),
                #f8fbff;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #061f3c 0%, #073b74 55%, #075da8 100%);
        }
        [data-testid="stSidebar"] * { color: #f6fbff; }
        [data-testid="stSidebar"] .stButton button {
            border: 1px solid rgba(255,255,255,.22);
            background: rgba(255,255,255,.10);
            color: white;
        }
        [data-testid="stSidebar"] .stButton button:hover {
            border-color: #6ed7ff;
            background: rgba(255,255,255,.18);
        }
        .block-container { max-width: 1180px; padding-top: 4.5rem; padding-bottom: 5rem; }
        .chatvns-hero {
            display: flex; align-items: center; gap: 1.25rem;
            padding: 1.15rem 1.35rem; margin-bottom: 1rem;
            background: linear-gradient(125deg, rgba(255,255,255,.96), rgba(232,247,255,.94));
            border: 1px solid rgba(8,119,232,.16); border-radius: 24px;
            box-shadow: 0 16px 44px rgba(7,59,116,.10);
        }
        .chatvns-hero img { width: 112px; height: 112px; object-fit: contain; }
        .chatvns-hero h1 { color: var(--chatvns-deep); margin: 0 0 .25rem; font-size: 2rem; }
        .chatvns-hero p { color: #49647f; margin: 0; line-height: 1.55; }
        .chatvns-kicker { color: var(--chatvns-blue); font-size: .76rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
        .chatvns-pill-row { display:flex; gap:.45rem; flex-wrap:wrap; margin-top:.65rem; }
        .chatvns-pill { padding:.3rem .65rem; border-radius:999px; background:#e7f4ff; color:#07579e; font-size:.78rem; font-weight:700; }
        .chatvns-welcome {
            text-align:center; max-width:720px; margin:2rem auto 1.2rem; padding:1.5rem;
        }
        .chatvns-welcome img { width:190px; filter: drop-shadow(0 16px 20px rgba(7,59,116,.16)); }
        .chatvns-welcome h2 { color:var(--chatvns-deep); margin:.6rem 0 .35rem; }
        .chatvns-welcome p { color:#5c7189; }
        [data-testid="stChatMessage"] {
            border: 1px solid rgba(8,119,232,.10); border-radius: 18px;
            background: rgba(255,255,255,.88); padding: .35rem .65rem;
            box-shadow: 0 7px 24px rgba(7,59,116,.055);
        }
        [data-testid="stChatInput"] { border-radius: 18px; }
        [data-testid="stMetric"] {
            background: rgba(255,255,255,.9); border:1px solid rgba(8,119,232,.12);
            padding:.8rem 1rem; border-radius:16px; box-shadow:0 7px 22px rgba(7,59,116,.06);
        }
        .chatvns-trust {
            display:flex; align-items:center; gap:.65rem; margin:.25rem 0 .7rem;
            color:#315879; font-size:.86rem;
        }
        .chatvns-trust img { width:48px; height:48px; object-fit:contain; }
        .chatvns-disclaimer {
            margin-top:1.4rem; padding:.85rem 1rem; border-radius:14px;
            background:#fff8e7; border:1px solid #f3d58b; color:#76551b; font-size:.84rem;
        }
        .chatvns-fresh { color:#0c7a55; font-weight:700; }
        .chatvns-stale { color:#b16a00; font-weight:700; }
        @media (max-width: 700px) {
            .chatvns-hero { align-items:flex-start; }
            .chatvns-hero img { width:78px; height:78px; }
            .chatvns-hero h1 { font-size:1.55rem; }
        }

        .stMainBlockContainer .stButton button {
            background: #FFFFFF;
            border: 1px solid #1976D2;
            color: #0A3D91;
        }
        .stMainBlockContainer .stButton button:hover {
            background: #1976D2;
            color: white;
        }

        .stBottom>* { background-color: unset; !important; }
        .stBottom .stChatInput>div {
            background: white;
            border: 2px solid #1976D2;
        }
        .stBottom .stChatInput>div:focus {
            border-color: #42A5F5;
            box-shadow: 0 0 0 4px rgba(66,165,245,.2);
        }
        .stBottom .stChatInput>div>div>div>div>div {
            background: white;
        }
        .stBottom .stChatInput textarea,
        .stBottom .stChatInput textarea::placeholder {
            color: #5c7189;
        }
        .stBottom .stChatInput button {
            background: #FFFFFF;
            border: 1px solid #1976D2;
            color: #0A3D91;
        }
        .stBottom .stChatInput button>svg,
        .stMetric>div>*,
        .stHeading>div h3 {
            color: #0A3D91;
        }
        .stExpander details summary {
            background-color: rgb(43, 44, 54);
        }
        .stElementContainer .stMarkdown {
            color: black;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(ticker_count: int, top_k: int) -> None:
    image_uri = mascot_data_uri("chatvns")
    st.markdown(
        f"""
        <section class="chatvns-hero">
          <img src="{image_uri}" alt="ChatVNS mascot">
          <div>
            <div class="chatvns-kicker">Trợ lý chứng khoán Việt Nam</div>
            <h1>ChatVNS</h1>
            <p>Trợ lý RAG cho dữ liệu chứng khoán Việt Nam — trả lời ngắn gọn, ưu tiên dữ liệu mới nhất và luôn chỉ rõ nguồn.</p>
            <div class="chatvns-pill-row">
              <span class="chatvns-pill">{ticker_count} mã có dữ liệu</span>
              <span class="chatvns-pill">Truy xuất kết hợp · Top {top_k}</span>
              <span class="chatvns-pill">Ưu tiên trích nguồn</span>
            </div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_welcome() -> None:
    image_uri = mascot_data_uri("welcome")
    st.markdown(
        f"""
        <section class="chatvns-welcome">
          <img src="{image_uri}" alt="ChatVNS welcome mascot">
          <h2>Chào bạn, mình là ChatVNS</h2>
          <p>Hỏi về giá gần nhất, báo cáo doanh nghiệp, tin tức hoặc chỉ báo kỹ thuật. Chọn một gợi ý bên dưới để bắt đầu.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_trust_note() -> None:
    image_uri = mascot_data_uri("trust")
    st.markdown(
        f"""
        <div class="chatvns-trust">
          <img src="{image_uri}" alt="Source trust mascot">
          <span>Nguồn được lấy từ dữ liệu đã thu thập và đưa trực tiếp vào ngữ cảnh của câu trả lời.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_disclaimer() -> None:
    st.markdown(
        """
        <div class="chatvns-disclaimer">
          <strong>Lưu ý:</strong> Nội dung do AI tổng hợp nhằm mục đích tham khảo, không phải khuyến nghị mua/bán hay tư vấn đầu tư cá nhân. Dữ liệu thị trường có thể có độ trễ; hãy kiểm tra lại với nguồn giao dịch chính thức trước khi ra quyết định.
        </div>
        """,
        unsafe_allow_html=True,
    )


def freshness_label(crawled_at: str | None) -> tuple[str, str]:
    if not crawled_at:
        return "Chưa xác định thời điểm cập nhật", "chatvns-stale"
    try:
        parsed = datetime.fromisoformat(str(crawled_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        minutes = max(0, int(age.total_seconds() // 60))
        if minutes < 60:
            return f"Cập nhật {minutes} phút trước", "chatvns-fresh"
        hours = minutes // 60
        if hours < 24:
            return f"Cập nhật {hours} giờ trước", "chatvns-fresh" if hours < 4 else "chatvns-stale"
        return f"Cập nhật {hours // 24} ngày trước", "chatvns-stale"
    except (TypeError, ValueError):
        return "Không đọc được thời điểm cập nhật", "chatvns-stale"


def apply_metric_card_style() -> None:
    if style_metric_cards is not None:
        style_metric_cards(
            background_color="#ffffff",
            border_left_color="#0877e8",
            border_color="#d8eaff",
            box_shadow=True,
        )


def render_section_header(label: str, description: str = "") -> None:
    st.subheader(label, divider="blue")
    if description:
        st.caption(description)
