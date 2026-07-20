"""Data Collector node — Tavily Search → Extract, with url_loader fallback."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from tavily import TavilyClient

from config.settings import settings


async def entry(state: dict[str, Any]) -> dict[str, Any]:
    """Collect real web data using Tavily SDK.

    Primary path:  TavilyClient.search() → TavilyClient.extract()
    Fallback path: Tavily Extract failed URLs → url_loader.fetch_multiple()

    Output format (backward-compatible with downstream):
        collection.raw_docs = [{title: str, url: str, content: str}, ...]
    """
    base: dict[str, Any] = state.get("base", {})
    collection: dict[str, Any] = state.get("collection", {})
    user_input = base.get("user_input", "")
    template_name = base.get("template_name", "deep_report")

    if not user_input:
        return state

    # ── Inject short-term memory context into RAG query ──────────────
    session_id = base.get("session_id", "")
    memory_context = ""
    if session_id and settings.rag_enabled:
        try:
            from infrastructure.memory.short_term import format_context, load_memory

            entries = await load_memory(user_input, session_id)
            if entries:
                memory_context = await format_context(entries)
                print(
                    f"[data_collector] short-term memory injected | session={session_id} | rounds={len(entries)}",
                    file=sys.stderr,
                    flush=True,
                )
        except Exception as e:
            print(
                f"[data_collector] short-term memory load failed: {e}", file=sys.stderr, flush=True
            )

    rag_query = f"{memory_context} {user_input}".strip() if memory_context else user_input

    # ── RAG retrieval (supplementary) ────────────────────────────────
    supplementary_docs = []
    if settings.rag_enabled:
        try:
            from retrieval.embedders.embedding_model import EmbeddingModel
            from retrieval.retrievers.hybrid_retriever import HybridRetriever
            from retrieval.vectorstores.qdrant_store import QdrantStore

            qdrant_settings = settings
            store = QdrantStore(
                host=qdrant_settings.qdrant_host,
                port=qdrant_settings.qdrant_port,
                api_key=qdrant_settings.qdrant_api_key,
            )
            embedder = EmbeddingModel.get_instance(qdrant_settings.embedding_model)
            retriever = HybridRetriever(store, embedder, collection="documents")

            rag_results = await retriever.search(rag_query, top_k=5)
            # Fetch source URLs from Qdrant payload for each RAG result
            rag_source_map: dict[str, str] = {}
            if rag_results:
                rag_point_ids = [r["id"] for r in rag_results if r.get("id")]
                if rag_point_ids:
                    try:
                        rag_payloads = await store.get_points("documents", rag_point_ids)
                        rag_source_map = {
                            p["id"]: p["payload"].get("source", "") for p in rag_payloads
                        }
                    except Exception:
                        pass
            for r in rag_results:
                doc_id = r.get("id", "")[:8]
                # Extract first sentence (up to 40 chars) for a meaningful label
                text = r.get("text", "")
                first_sentence = text.split("。")[0][:40] if "。" in text else text[:40]
                source_url = rag_source_map.get(r.get("id", ""), "")
                supplementary_docs.append(
                    {
                        "title": f"{first_sentence}... (chunk:{doc_id})",
                        "content": text,
                        "source": "rag",
                        "url": source_url,
                    }
                )
            print(
                f"[data_collector] RAG retrieval succeeded | query={rag_query[:80]} | results={len(supplementary_docs)}",
                file=sys.stderr,
                flush=True,
            )
        except Exception as exc:
            print(
                f"[data_collector] RAG retrieval failed, falling back to Tavily only | {exc}",
                file=sys.stderr,
                flush=True,
            )

    # ── 1. Search ────────────────────────────────────────────────────
    api_key = settings.tavily_api_key
    if not api_key:
        print("[data_collector] Tavily API key not configured", file=sys.stderr, flush=True)
        return _noop_result(collection, base)

    client = TavilyClient(api_key=api_key)

    try:
        search_params = _search_params(template_name)
        search_result = await asyncio.to_thread(client.search, query=user_input, **search_params)
        url_count = len(search_result.get("results", []))
        print(
            f"[data_collector] Tavily search succeeded | results={url_count}",
            file=sys.stderr,
            flush=True,
        )
    except Exception as exc:
        print(f"[data_collector] Tavily search failed: {exc}", file=sys.stderr, flush=True)
        return _noop_result(collection, base)

    # Build URL → title mapping from search results
    urls: list[str] = []
    url_title_map: dict[str, str] = {}
    for r in search_result.get("results", []):
        url = r.get("url", "")
        if url:
            urls.append(url)
            url_title_map[url] = r.get("title", "")

    if not urls:
        print("[data_collector] Tavily search returned no URLs", file=sys.stderr, flush=True)
        return _noop_result(collection, base)

    # ── 2. Extract (primary) ─────────────────────────────────────────
    try:
        extract_result = await asyncio.to_thread(
            client.extract, urls=urls, extract_depth="basic", format="markdown"
        )
        extract_ok = len(extract_result.get("results", []))
        extract_fail = len(extract_result.get("failed_results", []))
        print(
            f"[data_collector] Tavily extract succeeded | ok={extract_ok} failed={extract_fail}",
            file=sys.stderr,
            flush=True,
        )
    except Exception as exc:
        print(f"[data_collector] Tavily extract failed: {exc}", file=sys.stderr, flush=True)
        extract_result = {
            "results": [],
            "failed_results": [{"url": u, "error": str(exc)} for u in urls],
        }

    raw_docs: list[dict[str, str]] = []
    failed_urls: list[str] = []

    for r in extract_result.get("results", []):
        url = r.get("url", "")
        raw_docs.append(
            {
                "title": url_title_map.get(url, ""),
                "url": url,
                "content": r.get("raw_content", ""),
            }
        )

    # ── 2.5 Async index Tavily docs into Qdrant ────────────────────
    asyncio.create_task(_index_tavily_docs_to_qdrant(raw_docs, user_input))

    for f in extract_result.get("failed_results", []):
        failed_urls.append(f.get("url", ""))

    # ── 3. Fallback: url_loader for failed URLs ──────────────────────
    if failed_urls:
        try:
            from retrieval.loaders.url_loader import fetch_multiple

            pages = await fetch_multiple(failed_urls)
            print(
                f"[data_collector] url_loader fallback recovered {len(pages)} pages",
                file=sys.stderr,
                flush=True,
            )
            for page in pages:
                raw_docs.append(
                    {
                        "title": page.title or url_title_map.get(page.url, ""),
                        "url": page.url,
                        "content": page.text,
                    }
                )
        except Exception:
            pass

    if not raw_docs:
        print("[data_collector] no documents collected", file=sys.stderr, flush=True)
        return _noop_result(collection, base)

    # Merge RAG supplementary docs into raw_docs so they flow downstream
    raw_docs = supplementary_docs + raw_docs
    print(
        f"[data_collector] total docs collected: {len(raw_docs)} ({len(supplementary_docs)} rag + {len(raw_docs) - len(supplementary_docs)} tavily)",
        file=sys.stderr,
        flush=True,
    )

    source_urls: list[str] = []
    seen_urls: set[str] = set()
    for d in raw_docs:
        url = d.get("url", "")
        if url and (url.startswith("http://") or url.startswith("https://")):
            if url not in seen_urls:
                seen_urls.add(url)
                source_urls.append(url)
        # chunk 无真实 URL → 不加入引用，仅用于研报内容上下文
        """
        elif d.get("source") == "rag":
            rag_counter += 1
            source_urls.append(f"[知识库检索 #{rag_counter}] {d.get('title', 'RAG文档')}")
        """
    return {
        "collection": {
            "raw_docs": raw_docs,
            "compressed_summary": collection.get("compressed_summary", {}),
            "source_urls": source_urls,
        },
        "base": {**base, "status": "collecting"},
    }


def _noop_result(collection: dict, base: dict) -> dict:
    """Return state unchanged when search is unavailable."""
    return {
        "collection": {
            "raw_docs": [],
            "compressed_summary": collection.get("compressed_summary", {}),
            "source_urls": collection.get("source_urls", []),
            "supplementary_docs": collection.get("supplementary_docs", []),
        },
        "base": {**base, "status": "collecting"},
    }


def _search_params(template_name: str) -> dict[str, Any]:
    """Return search parameters tuned for the report template."""
    # Tavily 获取条数
    if template_name == "flash_news":
        return {"topic": "news", "max_results": 5}
    return {"search_depth": "advanced", "max_results": 7}


async def _index_tavily_docs_to_qdrant(
    raw_docs: list[dict[str, str]],
    user_input: str,
) -> None:
    """Chunk Tavily docs and index into Qdrant (fire-and-forget, non-blocking).

    Args:
        raw_docs: List of Tavily document dicts with url, content fields.
        user_input: Original user query (for logging context).
    """
    try:
        from config.settings import settings as _settings
        from retrieval.chunkers.paragraph_chunker import chunk_text
        from retrieval.vectorstores.qdrant_store import QdrantStore

        store = QdrantStore(
            host=_settings.qdrant_host,
            port=_settings.qdrant_port,
            api_key=_settings.qdrant_api_key,
        )
        from retrieval.embedders.embedding_model import EmbeddingModel

        embedder = EmbeddingModel.get_instance(_settings.embedding_model)

        all_chunks: list[str] = []
        all_sources: list[str] = []
        doc_count = 0

        for doc in raw_docs:
            content = doc.get("content", "")
            url = doc.get("url", doc.get("source", "unknown"))
            if not content or len(content) < 100:
                continue
            doc_count += 1
            result = chunk_text(content, source=url)
            for chunk in result.chunks:
                all_chunks.append(chunk.text)
                all_sources.append(url)

        if all_chunks:
            await store.upsert(
                collection="documents",
                texts=all_chunks,
                metas=[{"source": src, "chunk_index": i} for i, src in enumerate(all_sources)],
                embedder=embedder,
            )

        print(
            f"[data_collector] Qdrant index: {doc_count} Tavily docs → {len(all_chunks)} chunks written to collection 'documents' | query={user_input[:60]}",
            file=sys.stderr,
            flush=True,
        )
    except Exception as exc:
        print(
            f"[data_collector] Qdrant index failed (non-blocking) | {exc}",
            file=sys.stderr,
            flush=True,
        )
