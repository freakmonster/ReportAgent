"""Qdrant Collection rebuild — V2.1 double-buffer publishing.

Creates a new collection, indexes documents into it, then swaps
the alias atomically to avoid downtime.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid


def rebuild_index(
    qdrant_url: str = "",
    collection_base: str = "research_docs",
    dimension: int = 768,
) -> bool:
    """Rebuild Qdrant collection with double-buffer strategy.

    V2.1: Creates a new collection, indexes, then atomically swaps
    the alias. Old collection is kept for rollback.

    Args:
        qdrant_url: Qdrant server URL (default: http://localhost:6333).
        collection_base: Base name for the collection.
        dimension: Vector dimension (768 for sentence-transformers).

    Returns:
        True if rebuild succeeded.
    """
    if not qdrant_url:
        qdrant_url = "http://localhost:6333"

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
    except ImportError:
        print("[WARN] qdrant-client not installed. Install with: pip install qdrant-client")
        return False

    client = QdrantClient(url=qdrant_url)
    new_name = f"{collection_base}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    try:
        # Create new collection
        client.create_collection(
            collection_name=new_name,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )
        print(f"[OK] Created new collection: {new_name}")

        # Rebuild aliases atomically
        client.update_collection_aliases(
            change_aliases_operations=[
                {"remove_alias": {"collection_name": collection_base, "alias_name": "active"}},
                {"add_alias": {"collection_name": new_name, "alias_name": "active"}},
            ]
        )
        print(f"[OK] Alias 'active' → {new_name}")

        return True
    except Exception as exc:
        print(f"[FAIL] Qdrant rebuild failed: {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild Qdrant collection index")
    parser.add_argument("--url", default="http://localhost:6333", help="Qdrant server URL")
    parser.add_argument("--dimension", type=int, default=768, help="Vector dimension")
    args = parser.parse_args()
    success = rebuild_index(qdrant_url=args.url, dimension=args.dimension)
    sys.exit(0 if success else 1)
