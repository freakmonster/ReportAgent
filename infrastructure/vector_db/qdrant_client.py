"""Qdrant async client wrapper for vector database operations."""

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models

from config.settings import settings

# ── Module-level client ─────────────────────────────────────
_qdrant_client: AsyncQdrantClient | None = None


async def init_qdrant() -> None:
    """Initialise the Qdrant async client."""
    global _qdrant_client

    host = settings.qdrant_host
    port = settings.qdrant_port
    api_key = settings.qdrant_api_key

    if api_key:
        _qdrant_client = AsyncQdrantClient(
            host=host,
            port=port,
            api_key=api_key,
        )
    else:
        _qdrant_client = AsyncQdrantClient(
            host=host,
            port=port,
        )


async def close_qdrant() -> None:
    """Close the Qdrant client connection."""
    global _qdrant_client

    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None


def get_qdrant() -> AsyncQdrantClient:
    """Return the shared Qdrant client instance."""
    if _qdrant_client is None:
        raise RuntimeError(
            "Qdrant not initialised. Call init_qdrant() before get_qdrant()."
        )
    return _qdrant_client


async def collection_exists(name: str) -> bool:
    """Check whether a collection with the given name exists."""
    client = get_qdrant()
    try:
        collections_response = await client.get_collections()
        collection_names = [
            c.name for c in collections_response.collections
        ]
        return name in collection_names
    except Exception:
        return False


async def ensure_collection(
    name: str,
    vector_size: int = 1024,
    distance: qdrant_models.Distance = qdrant_models.Distance.COSINE,
) -> None:
    """Ensure a collection exists, creating it if it does not.

    Uses bge-m3 embedding size (1024) by default.
    """
    client = get_qdrant()
    exists = await collection_exists(name)
    if not exists:
        await client.create_collection(
            collection_name=name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_size,
                distance=distance,
            ),
        )
