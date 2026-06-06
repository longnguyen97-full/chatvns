from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QA_MARKDOWN_PATH = PROJECT_ROOT / "documents" / "Q&A.md"
QA_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "q&a.json"

DEFAULT_SUGGESTED_QUESTIONS = [
    {
        "category": "Tổng quan",
        "questions": [
            "Tóm tắt nhanh cổ phiếu HPG hiện tại",
            "Tóm tắt nhanh cổ phiếu FPT hiện tại",
            "Tóm tắt nhanh cổ phiếu VCB hiện tại",
        ],
    },
    {
        "category": "Phân tích doanh nghiệp",
        "questions": [
            "HPG đang có những luận điểm đầu tư nào nổi bật?",
            "FPT có những động lực tăng trưởng nào trong năm nay?",
            "VCB có điểm mạnh và rủi ro gì trong các báo cáo gần đây?",
        ],
    },
    {
        "category": "Tin tức và sự kiện",
        "questions": [
            "Tin tức mới gần đây của HPG ảnh hưởng gì đến cổ phiếu?",
            "Sự kiện doanh nghiệp nào đang đáng chú ý với FPT?",
            "Tổng hợp tin tức nổi bật gần đây của VCB",
        ],
    },
    {
        "category": "So sánh và đánh giá",
        "questions": [
            "So sánh nhanh HPG và FPT cho mục tiêu đầu tư trung hạn",
            "So sánh HPG, FPT, VCB theo dữ liệu hiện có",
            "Cổ phiếu nào đang có bối cảnh ổn định hơn giữa FPT và VCB?",
        ],
    },
]


def normalize_suggestions(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        suggestions = payload.get("suggested_questions", [])
    elif isinstance(payload, list):
        suggestions = payload
    else:
        suggestions = []

    normalized: list[dict] = []
    for group in suggestions:
        if not isinstance(group, dict):
            continue
        category = str(group.get("category") or "Gợi ý").strip()
        questions = [
            str(question).strip()
            for question in group.get("questions", [])
            if str(question).strip()
        ]
        if questions:
            normalized.append({"category": category, "questions": questions})
    return normalized


def parse_markdown_suggestions(markdown_text: str) -> list[dict]:
    groups: list[dict] = []
    current_category: str | None = None
    current_questions: list[str] = []

    def flush() -> None:
        nonlocal current_category, current_questions
        if current_category and current_questions:
            groups.append({"category": current_category, "questions": current_questions})
        current_category = None
        current_questions = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            flush()
            current_category = line.lstrip("#").strip()
            continue
        if line.startswith(("- ", "* ")):
            question = line[2:].strip()
            if not question:
                continue
            if current_category is None:
                current_category = "Goi y"
            current_questions.append(question)

    flush()
    return groups


def load_suggested_questions() -> list[dict]:
    if QA_JSON_PATH.exists():
        try:
            payload = json.loads(QA_JSON_PATH.read_text(encoding="utf-8"))
            normalized = normalize_suggestions(payload)
            if normalized:
                return normalized
        except (OSError, json.JSONDecodeError):
            pass

    if QA_MARKDOWN_PATH.exists():
        try:
            normalized = parse_markdown_suggestions(QA_MARKDOWN_PATH.read_text(encoding="utf-8"))
            if normalized:
                return normalized
        except OSError:
            pass

    return DEFAULT_SUGGESTED_QUESTIONS


def export_suggested_questions_json(
    markdown_path: Path = QA_MARKDOWN_PATH,
    json_path: Path = QA_JSON_PATH,
) -> list[dict]:
    if markdown_path.exists():
        try:
            normalized = parse_markdown_suggestions(markdown_path.read_text(encoding="utf-8"))
        except OSError:
            normalized = []
    else:
        normalized = []

    if not normalized:
        normalized = DEFAULT_SUGGESTED_QUESTIONS

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"suggested_questions": normalized}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized
