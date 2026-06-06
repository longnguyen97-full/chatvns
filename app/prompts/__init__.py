from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()
