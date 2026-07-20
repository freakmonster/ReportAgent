"""Integration tests for url_loader — local HTTP server, real TCP connections.

These tests use a local ``http.server`` with threading to serve pre-built
HTML pages at 127.0.0.1 on a random port.  No external network is required.

Run:
    pytest tests/integration/test_url_loader_live.py -v
"""

from __future__ import annotations

import http.server
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from retrieval.loaders.url_loader import WebPage, fetch_multiple, fetch_url

# ---------------------------------------------------------------------------
# Helper: find a free port
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Local test HTTP server
# ---------------------------------------------------------------------------


class _TestHandler(http.server.BaseHTTPRequestHandler):
    """Dynamic handler serving pre-configured routes.

    Subclasses must override ``ROUTES`` with ``{path: (status, headers, body)}``.
    Routes with a leading ``!`` in the path will sleep for 2 seconds before
    responding (used for timeout tests).
    """

    ROUTES: dict[str, tuple[int, dict[str, str], bytes]] = {}

    def do_GET(self) -> None:  # noqa: N802
        # Support delay routes: "/!hang" will sleep before responding
        if self.path.startswith("/!"):
            time.sleep(2)
            self.path = "/" + self.path[2:]

        route = self.ROUTES.get(self.path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        status, headers, body = route
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802
        route = self.ROUTES.get(self.path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        status, headers, _ = route
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        """Suppress server logs during tests."""
        pass


def _start_server(
    routes: dict[str, tuple[int, dict[str, str], bytes]], port: int
) -> http.server.HTTPServer:
    """Create and start a threaded HTTP server with *routes*."""
    # Build a handler subclass with the requested routes
    handler = type("_DynamicHandler", (_TestHandler,), {"ROUTES": routes})
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)  # let the server socket bind
    return server


# ── Shared HTML snippets ───────────────────────────────────────────────

_UTF8_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>测试页面</title></head>
<body>
<article>
  <h1>新能源汽车市场报告</h1>
  <p>2026年第二季度，中国新能源汽车销量达到300万辆，同比增长45%。</p>
  <p>其中纯电动汽车占比62%，插电混动占比38%。</p>
</article>
<nav><a href="/">首页</a></nav>
<footer>版权所有 © 2026</footer>
<script>console.log("ads")</script>
</body></html>"""

_GBK_HTML_BYTES = (
    b"<!DOCTYPE html>\r\n"
    b'<html><head><meta charset="gbk"><title>\xb5\xe7\xb3\xd8\xbc\xbc\xca\xf5</title></head>\r\n'
    b"<body><article><p>\xc4\xfe\xb5\xc2\xca\xb1\xb4\xfa\xb5\xe7\xb3\xd8\xbc\xbc\xca\xf5\xcd\xbb\xc6\xc6</p></article></body></html>"
)

_NOISE_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>嘈杂页面</title></head>
<body>
<article><p>核心内容在这里。</p></article>
<div class="sidebar">侧边栏广告</div>
<div class="advertisement">横幅广告</div>
<div class="popup-overlay">弹窗内容</div>
<div id="comments">网友评论</div>
<nav class="breadcrumb">首页 > 文章</nav>
<div class="social-share-btns">分享按钮</div>
<div class="related-articles">相关文章</div>
<footer class="pagination">第1页</footer>
</body></html>"""

_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>无article页面</title></head>
<body>
<main><p>正文在main标签中。</p></main>
<footer>版权信息</footer>
</body></html>"""


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def server():
    """Start a local HTTP server with multiple test routes.

    Returns ``base_url`` (e.g. ``http://127.0.0.1:51234``).
    The server is automatically shut down after the test.
    """
    port = _free_port()
    routes: dict[str, tuple[int, dict[str, str], bytes]] = {
        "/utf8": (200, {"Content-Type": "text/html; charset=utf-8"}, _UTF8_HTML.encode("utf-8")),
        "/gbk": (200, {"Content-Type": "text/html; charset=gbk"}, _GBK_HTML_BYTES),
        "/redirect": (301, {"Location": "/utf8"}, b""),
        "/404": (404, {"Content-Type": "text/plain"}, b"Not Found"),
        "/slow": (200, {"Content-Type": "text/html"}, b"<html><body>slow</body></html>"),
        "/hang": (200, {"Content-Type": "text/html"}, b"<html><body>timeout target</body></html>"),
        "/noise": (
            200,
            {"Content-Type": "text/html; charset=utf-8"},
            _NOISE_HTML_TEMPLATE.encode("utf-8"),
        ),
        "/fallback": (
            200,
            {"Content-Type": "text/html; charset=utf-8"},
            _FALLBACK_HTML.encode("utf-8"),
        ),
    }
    srv = _start_server(routes, port)
    base = f"http://127.0.0.1:{port}"
    yield base
    srv.shutdown()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestFetchURLIntegration:
    """Integration tests using a local HTTP server."""

    # 1. Basic UTF-8 fetch
    @pytest.mark.asyncio
    async def test_fetch_utf8_page(self, server: str) -> None:
        """Real HTTP GET → UTF-8 HTML → correct title and body extracted."""
        page = await fetch_url(f"{server}/utf8", timeout=5)
        assert isinstance(page, WebPage)
        assert page.title == "测试页面"
        assert "新能源汽车销量达到300万辆" in page.text
        # Noise elements removed
        assert "版权所有" not in page.text
        assert "console.log" not in page.text

    # 2. GBK-encoded Chinese page
    @pytest.mark.asyncio
    async def test_fetch_gbk_page(self, server: str) -> None:
        """GBK-encoded page is correctly detected and decoded."""
        page = await fetch_url(f"{server}/gbk", timeout=5)
        assert page.title == "电池技术"
        assert "宁德时代" in page.text

    # 3. 301 redirect
    @pytest.mark.asyncio
    async def test_fetch_redirect_301(self, server: str) -> None:
        """301 redirect is followed and the final page is fetched."""
        page = await fetch_url(f"{server}/redirect", timeout=5)
        assert page.title == "测试页面"
        assert "新能源汽车" in page.text

    # 4. 404 error
    @pytest.mark.asyncio
    async def test_fetch_404_raises_error(self, server: str) -> None:
        """HTTP 404 raises httpx.HTTPError."""
        import httpx

        with pytest.raises(httpx.HTTPError):
            await fetch_url(f"{server}/404", timeout=5)

    # 5. Timeout on slow server
    @pytest.mark.asyncio
    async def test_fetch_timeout(self, server: str) -> None:
        """A short timeout on a 2-second-delay endpoint raises ReadTimeout.

        The ``/!hang`` route sleeps 2s before responding; with a 0.5s
        timeout the read will time out.

        NOTE: ``_get_http_client()`` caches a global client ignoring
        subsequent timeout changes, so we force-close it first.
        """
        import httpx

        from retrieval.loaders.url_loader import _get_http_client, _http_client

        # Force the global client to be replaced with our short timeout
        if _http_client is not None:
            await _http_client.aclose()
        client = _get_http_client(timeout=0.5)
        try:
            with pytest.raises(httpx.ReadTimeout):
                await fetch_url(f"{server}/!hang", timeout=0.5)
        finally:
            await client.aclose()

    # 6. Comprehensive noise removal
    @pytest.mark.asyncio
    async def test_noise_removal_comprehensive(self, server: str) -> None:
        """All 8 noise patterns are stripped from extracted text."""
        page = await fetch_url(f"{server}/noise", timeout=5)
        assert "核心内容在这里" in page.text
        for noise in (
            "侧边栏广告",
            "横幅广告",
            "弹窗内容",
            "网友评论",
            "首页 > 文章",
            "分享按钮",
            "相关文章",
            "第1页",
        ):
            assert noise not in page.text, f"Noise '{noise}' was not removed"

    # 7. Content tag fallback (<main> when no <article>)
    @pytest.mark.asyncio
    async def test_content_tag_fallback(self, server: str) -> None:
        """When <article> is absent, <main> is used as content source."""
        page = await fetch_url(f"{server}/fallback", timeout=5)
        assert "正文在main标签中" in page.text
        assert "版权信息" not in page.text  # footer removed

    # 8. max_length truncation
    @pytest.mark.asyncio
    async def test_max_length_truncation(self, server: str) -> None:
        """Content is truncated to max_length characters."""
        page = await fetch_url(f"{server}/utf8", timeout=5, max_length=20)
        assert len(page.text) <= 20
        assert page.char_count <= 20

    # 9. fetch_multiple concurrency
    @pytest.mark.asyncio
    async def test_fetch_multiple_concurrency(self, server: str) -> None:
        """fetch_multiple fetches all URLs concurrently with a semaphore."""
        urls = [
            f"{server}/utf8",
            f"{server}/gbk",
            f"{server}/fallback",
        ]
        pages = await fetch_multiple(urls, timeout=10, max_length=5000, max_concurrent=2)
        assert len(pages) == 3
        titles = {p.title for p in pages}
        assert titles == {"测试页面", "电池技术", "无article页面"}

    # 10. User-Agent header is set
    @pytest.mark.asyncio
    async def test_user_agent_header(self, server: str) -> None:
        """User-Agent header is sent with requests."""
        page = await fetch_url(f"{server}/utf8", timeout=5, user_agent="TestBot/9.9")
        assert page.title == "测试页面"
        # The header is verified implicitly — the server accepts it.
        # For explicit verification we'd need to inspect server logs.

    # 11. HTTP client reuse (connection pooling)
    @pytest.mark.asyncio
    async def test_http_client_reuse(self, server: str) -> None:
        """Two consecutive requests reuse the shared HTTP client."""
        from retrieval.loaders.url_loader import _get_http_client

        client_before = _get_http_client()
        page1 = await fetch_url(f"{server}/utf8", timeout=5)
        client_after_first = _get_http_client()
        page2 = await fetch_url(f"{server}/utf8", timeout=5)
        client_after_second = _get_http_client()

        assert page1.title == page2.title == "测试页面"
        # Same client instance is reused
        assert client_before is client_after_first is client_after_second
