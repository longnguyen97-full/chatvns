from __future__ import annotations

import re


TEXT_EXTENSIONS = {".txt", ".html", ".csv", ".json", ".md"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TOKEN_PATTERN = re.compile(r"[\wÀ-ỹ]+|[^\w\s]", flags=re.UNICODE)
BOILERPLATE_LINES = {
    "viết bài",
    "tiện ích",
    "sách",
    "cá nhân hóa",
    "tùy chỉnh",
    "dành cho bạn",
    "live",
    "xem thêm",
    "tải về",
    "đang tải",
    "bình luận",
    "video",
    "mới",
    "hot nhất",
    "mới nhất",
    "liên hệ",
    "về chúng tôi",
    "chính sách và điều khoản",
}
