from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "stockqa_chunks")

HF_API_KEY = (
    os.getenv("HF_API_KEY")
    or os.getenv("HG_API_KEY")
    or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    or ""
)
if HF_API_KEY:
    os.environ.setdefault("HF_TOKEN", HF_API_KEY)
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", HF_API_KEY)

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "BAAI/bge-m3",
)
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
EMBEDDING_PROVIDER = "hf_api"
HF_INFERENCE_PROVIDER = os.getenv("HF_INFERENCE_PROVIDER", "hf-inference")
EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "")
EMBEDDING_API_TIMEOUT = float(os.getenv("EMBEDDING_API_TIMEOUT", "60"))
EMBEDDING_API_RETRIES = int(os.getenv("EMBEDDING_API_RETRIES", "3"))
EMBEDDING_API_RETRY_BACKOFF = float(os.getenv("EMBEDDING_API_RETRY_BACKOFF", "2"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))
EMBEDDING_CACHE_ENABLED = os.getenv("EMBEDDING_CACHE_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
EMBEDDING_CACHE_PATH = Path(os.getenv("EMBEDDING_CACHE_PATH", str(PROCESSED_DIR / "embedding_cache.sqlite3")))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DEFAULT_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "180"))
DEFAULT_TOP_K = int(os.getenv("TOP_K", "5"))

RERANK_ENABLED = os.getenv("RERANK_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_CANDIDATE_LIMIT = int(os.getenv("RERANK_CANDIDATE_LIMIT", "8"))
RERANK_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "16"))
RERANK_API_URL = os.getenv(
    "RERANK_API_URL",
    f"https://router.huggingface.co/hf-inference/models/{RERANK_MODEL}",
)
RERANK_API_TIMEOUT = float(os.getenv("RERANK_API_TIMEOUT", "60"))

CONTEXT_COMPRESSION_ENABLED = os.getenv("CONTEXT_COMPRESSION_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
CONTEXT_MAX_SENTENCES_PER_CHUNK = int(os.getenv("CONTEXT_MAX_SENTENCES_PER_CHUNK", "5"))
CONTEXT_MAX_CHARS_PER_CHUNK = int(os.getenv("CONTEXT_MAX_CHARS_PER_CHUNK", "1400"))
CONTEXT_MIN_SENTENCE_CHARS = int(os.getenv("CONTEXT_MIN_SENTENCE_CHARS", "32"))
