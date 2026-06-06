from __future__ import annotations

from collections.abc import Callable

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import (
    EMBEDDING_API_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CACHE_ENABLED,
    EMBEDDING_CACHE_PATH,
    EMBEDDING_MODEL,
    QDRANT_COLLECTION,
    QDRANT_URL,
)
from app.embedding_cache import EmbeddingCache, embedding_cache_key
from app.embeddings import get_embedding_model
from app.schemas import Chunk, RetrievedChunk


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    collections = client.get_collections().collections
    if any(collection.name == QDRANT_COLLECTION for collection in collections):
        return
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def recreate_collection(client: QdrantClient, vector_size: int) -> None:
    collections = client.get_collections().collections
    if any(collection.name == QDRANT_COLLECTION for collection in collections):
        client.delete_collection(collection_name=QDRANT_COLLECTION)
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def chunk_payload(chunk: Chunk) -> dict:
    return {
        "text": chunk.text,
        "ticker": chunk.ticker,
        "scope": chunk.scope,
        "modality": chunk.modality,
        "source_path": chunk.source_path,
        "chunk_index": chunk.chunk_index,
        "structure_type": chunk.structure_type,
        "heading_path": chunk.heading_path,
        "token_count": chunk.token_count,
        "metadata": chunk.metadata,
    }


def index_chunks(
    chunks: list[Chunk],
    batch_size: int | None = None,
    rebuild: bool = True,
    progress_callback: Callable[[dict], None] | None = None,
) -> int:
    batch_size = batch_size or EMBEDDING_BATCH_SIZE
    embedding_model = get_embedding_model()
    cache = EmbeddingCache(EMBEDDING_CACHE_PATH) if EMBEDDING_CACHE_ENABLED else None
    client = get_qdrant_client()
    try:
        if rebuild:
            recreate_collection(client, embedding_model.dim)
        else:
            ensure_collection(client, embedding_model.dim)

        indexed = 0
        total_batches = (len(chunks) + batch_size - 1) // batch_size if chunks else 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            batch_number = (start // batch_size) + 1
            vectors, cache_hits, cache_misses = embed_index_batch(batch, embedding_model, cache)
            if progress_callback:
                progress_callback(
                    {
                        "stage": "embedding",
                        "batch_number": batch_number,
                        "total_batches": total_batches,
                        "batch_size": len(batch),
                        "indexed_so_far": indexed,
                        "total_chunks": len(chunks),
                        "embedding_dim": embedding_model.dim,
                        "cache_hits": cache_hits,
                        "cache_misses": cache_misses,
                    }
                )
            points = [
                PointStruct(id=chunk.id, vector=vector, payload=chunk_payload(chunk))
                for chunk, vector in zip(batch, vectors)
            ]
            client.upsert(collection_name=QDRANT_COLLECTION, points=points)
            indexed += len(points)
            if progress_callback:
                progress_callback(
                    {
                        "stage": "upsert",
                        "batch_number": batch_number,
                        "total_batches": total_batches,
                        "batch_size": len(points),
                        "indexed_so_far": indexed,
                        "total_chunks": len(chunks),
                        "embedding_dim": embedding_model.dim,
                        "cache_hits": cache_hits,
                        "cache_misses": cache_misses,
                    }
                )
        return indexed
    finally:
        if cache:
            cache.close()


def embed_index_batch(
    batch: list[Chunk],
    embedding_model,
    cache: EmbeddingCache | None,
) -> tuple[list[list[float]], int, int]:
    if not cache:
        return embedding_model.encode([chunk.text for chunk in batch]), 0, len(batch)

    keys = [
        embedding_cache_key(
            chunk.text,
            provider=embedding_model.provider,
            model=EMBEDDING_MODEL,
            dim=embedding_model.dim,
            api_url=EMBEDDING_API_URL,
        )
        for chunk in batch
    ]
    cached = cache.get_many(keys)
    missing_indexes = [index for index, key in enumerate(keys) if key not in cached]

    if missing_indexes:
        missing_vectors = embedding_model.encode([batch[index].text for index in missing_indexes])
        cache.set_many(
            {
                keys[index]: vector
                for index, vector in zip(missing_indexes, missing_vectors)
            }
        )
        for index, vector in zip(missing_indexes, missing_vectors):
            cached[keys[index]] = vector

    return [cached[key] for key in keys], len(batch) - len(missing_indexes), len(missing_indexes)


def search_points(
    client: QdrantClient,
    query_vector: list[float],
    query_filter: Filter | None,
    limit: int,
):
    if hasattr(client, "search"):
        return client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

    response = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    return response.points


def retrieve(query: str, top_k: int, ticker: str | None = None) -> list[RetrievedChunk]:
    embedding_model = get_embedding_model()
    client = get_qdrant_client()
    ensure_collection(client, embedding_model.dim)

    query_filter = None
    if ticker:
        query_filter = Filter(
            must=[FieldCondition(key="ticker", match=MatchValue(value=ticker.upper()))]
        )

    hits = search_points(
        client=client,
        query_vector=embedding_model.encode([query])[0],
        query_filter=query_filter,
        limit=top_k,
    )
    retrieved: list[RetrievedChunk] = []
    for hit in hits:
        payload = hit.payload or {}
        source_path = str(payload.get("source_path", ""))
        ticker_value = str(payload.get("ticker", ""))
        scope = str(payload.get("scope") or ticker_value or "")
        if ticker_value.upper() == "MARKET" or "world_market" in source_path or "/market/" in source_path.replace("\\", "/"):
            ticker_value = ""
            scope = "market"
        retrieved.append(
            RetrievedChunk(
                id=str(hit.id),
                text=str(payload.get("text", "")),
                score=float(hit.score),
                ticker=ticker_value,
                modality=str(payload.get("modality", "")),
                source_path=source_path,
                structure_type=str(payload.get("structure_type", "")),
                heading_path=list(payload.get("heading_path") or []),
                metadata=dict(payload.get("metadata") or {}),
                scope=scope,
            )
        )
    return retrieved
