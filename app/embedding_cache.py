from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                cache_key TEXT PRIMARY KEY,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        if not keys:
            return {}

        found: dict[str, list[float]] = {}
        for start in range(0, len(keys), 900):
            chunk = keys[start : start + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = self._connection.execute(
                f"SELECT cache_key, vector_json FROM embeddings WHERE cache_key IN ({placeholders})",
                chunk,
            ).fetchall()
            for cache_key, vector_json in rows:
                found[str(cache_key)] = [float(value) for value in json.loads(vector_json)]
        return found

    def set_many(self, values: dict[str, list[float]]) -> None:
        if not values:
            return

        rows = [
            (cache_key, json.dumps(vector, separators=(",", ":")))
            for cache_key, vector in values.items()
        ]
        self._connection.executemany(
            """
            INSERT OR REPLACE INTO embeddings (cache_key, vector_json)
            VALUES (?, ?)
            """,
            rows,
        )
        self._connection.commit()


def embedding_cache_key(
    text: str,
    *,
    provider: str,
    model: str,
    dim: int,
    api_url: str,
) -> str:
    payload = "\n".join(
        [
            f"provider={provider}",
            f"model={model}",
            f"dim={dim}",
            f"api_url={api_url}",
            text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
