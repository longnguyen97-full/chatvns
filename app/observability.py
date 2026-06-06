from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR


INTERACTION_LOG_PATH = DATA_DIR / "logs" / "chatbot_interactions.jsonl"


def append_interaction_log(event: dict[str, Any], path: Path = INTERACTION_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_interaction_logs(path: Path = INTERACTION_LOG_PATH, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)

    if limit is None:
        return rows
    return rows[-limit:]
