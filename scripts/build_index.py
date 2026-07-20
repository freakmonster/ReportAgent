#!/usr/bin/env python3
"""CLI script to build a RAG index from URLs or text sources.

Usage:
    # Build from a single URL
    python -m scripts.build_index --collection reports --url "https://example.com/doc"

    # Build from a file containing URLs (one per line)
    python -m scripts.build_index --collection reports --urls-file urls.txt

    # Build from inline text
    python -m scripts.build_index --collection reports --text "Some document text here..."
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def _build_from_urls(collection_name: str, urls: list[str]) -> None:
    """Build index from URL list."""
    from config.settings import settings
    from retrieval.pipelines.build_index import IndexBuilder
    from retrieval.vectorstores.qdrant_store import QdrantStore

    store = QdrantStore(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key,
    )
    builder = IndexBuilder(qdrant_store=store, base_collection=collection_name)
    result = await builder.build_from_urls(urls)

    # Update index_repo status
    try:
        from infrastructure.database.connection import init_db
        from infrastructure.database.repositories.index_repo import (
            get_index_repo,
            init_index_repo,
        )

        await init_db()
        from infrastructure.database.connection import _get_session_factory

        init_index_repo(_get_session_factory())

        if result.errors:
            await get_index_repo().mark_failed(collection_name, str(result.errors))
        else:
            checksum = str(hash(tuple(urls)))
            await get_index_repo().mark_ready(collection_name, result.doc_count, checksum)
    except Exception as exc:
        print(f"[WARN] Failed to update index_repo: {exc}", file=sys.stderr)

    print(f"Build result: {result.doc_count} docs, {result.chunk_count} chunks")
    if result.errors:
        for err in result.errors:
            print(f"  Error: {err}", file=sys.stderr)


async def _build_from_texts(collection_name: str, texts: list[str]) -> None:
    """Build index from text list."""
    from config.settings import settings
    from retrieval.pipelines.build_index import IndexBuilder
    from retrieval.vectorstores.qdrant_store import QdrantStore

    store = QdrantStore(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key,
    )
    builder = IndexBuilder(qdrant_store=store, base_collection=collection_name)
    result = await builder.build_from_texts(texts)

    # Update index_repo status
    try:
        from infrastructure.database.connection import init_db
        from infrastructure.database.repositories.index_repo import (
            get_index_repo,
            init_index_repo,
        )

        await init_db()
        from infrastructure.database.connection import _get_session_factory

        init_index_repo(_get_session_factory())

        if result.errors:
            await get_index_repo().mark_failed(collection_name, str(result.errors))
        else:
            checksum = str(hash("".join(texts)))
            await get_index_repo().mark_ready(collection_name, result.doc_count, checksum)
    except Exception as exc:
        print(f"[WARN] Failed to update index_repo: {exc}", file=sys.stderr)

    print(f"Build result: {result.doc_count} docs, {result.chunk_count} chunks")
    if result.errors:
        for err in result.errors:
            print(f"  Error: {err}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAG index from sources")
    parser.add_argument("--collection", default="documents", help="Qdrant collection name")
    parser.add_argument("--url", help="Single URL to index")
    parser.add_argument("--urls-file", help="File containing URLs (one per line)")
    parser.add_argument("--text", help="Inline text to index")
    args = parser.parse_args()

    if not any([args.url, args.urls_file, args.text]):
        parser.print_help()
        sys.exit(1)

    if args.url:
        asyncio.run(_build_from_urls(args.collection, [args.url]))
    elif args.urls_file:
        with open(args.urls_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
        asyncio.run(_build_from_urls(args.collection, urls))
    elif args.text:
        asyncio.run(_build_from_texts(args.collection, [args.text]))


if __name__ == "__main__":
    main()
