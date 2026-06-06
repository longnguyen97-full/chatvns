from __future__ import annotations

import math
import time
from functools import lru_cache

import httpx
from huggingface_hub import InferenceClient

from app.config import (
    EMBEDDING_API_RETRIES,
    EMBEDDING_API_RETRY_BACKOFF,
    EMBEDDING_API_TIMEOUT,
    EMBEDDING_API_URL,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    HF_API_KEY,
    HF_INFERENCE_PROVIDER,
)


class EmbeddingModel:
    def __init__(self) -> None:
        self.dim = EMBEDDING_DIM
        self.provider = EMBEDDING_PROVIDER

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self.provider != "hf_api":
            raise RuntimeError("Local embedding providers are disabled. Use Hugging Face API only.")
        return self._api_embedding(texts)

    def _api_embedding(self, texts: list[str]) -> list[list[float]]:
        if not HF_API_KEY:
            raise RuntimeError("HF_API_KEY is required for Hugging Face API embeddings")
        if not texts:
            return []

        client_kwargs = {"api_key": HF_API_KEY, "timeout": EMBEDDING_API_TIMEOUT}
        if EMBEDDING_API_URL:
            client = InferenceClient(model=EMBEDDING_API_URL, **client_kwargs)
            model = None
        else:
            client = InferenceClient(provider=HF_INFERENCE_PROVIDER, **client_kwargs)
            model = EMBEDDING_MODEL

        payload = self._feature_extraction_with_retry(client, texts, model)
        if hasattr(payload, "tolist"):
            payload = payload.tolist()

        vectors = self._coerce_api_vectors(payload, expected_count=len(texts))
        return [self._normalize_vector(vector) for vector in vectors]

    def _feature_extraction_with_retry(self, client: InferenceClient, texts: list[str], model: str | None):
        attempts = max(1, EMBEDDING_API_RETRIES)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return client.feature_extraction(texts, model=model)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == attempts:
                    break
                time.sleep(EMBEDDING_API_RETRY_BACKOFF * attempt)
        raise RuntimeError(
            "Hugging Face embedding request timed out. "
            "Try lowering EMBEDDING_BATCH_SIZE or increasing EMBEDDING_API_TIMEOUT."
        ) from last_error

    def _coerce_api_vectors(self, payload, expected_count: int) -> list[list[float]]:
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected embedding API response: {type(payload).__name__}")
        if expected_count == 1 and self._is_vector(payload):
            return [self._fit_dimension([float(value) for value in payload])]
        if len(payload) != expected_count:
            raise RuntimeError(f"Expected {expected_count} embeddings, received {len(payload)}")

        vectors = []
        for item in payload:
            if self._is_vector(item):
                vectors.append(self._fit_dimension([float(value) for value in item]))
            elif isinstance(item, list) and item and all(self._is_vector(token_vector) for token_vector in item):
                vectors.append(self._fit_dimension(self._mean_pool(item)))
            else:
                raise RuntimeError("Unexpected embedding vector shape from API")
        return vectors

    def _is_vector(self, value) -> bool:
        return isinstance(value, list) and all(isinstance(item, int | float) for item in value)

    def _mean_pool(self, token_vectors: list[list[float]]) -> list[float]:
        width = len(token_vectors[0])
        pooled = []
        for index in range(width):
            pooled.append(sum(float(vector[index]) for vector in token_vectors) / len(token_vectors))
        return pooled

    def _fit_dimension(self, vector: list[float]) -> list[float]:
        if len(vector) == self.dim:
            return vector
        if len(vector) > self.dim:
            return vector[: self.dim]
        return vector + [0.0] * (self.dim - len(vector))

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


@lru_cache(maxsize=1)
def get_embedding_model() -> EmbeddingModel:
    return EmbeddingModel()
