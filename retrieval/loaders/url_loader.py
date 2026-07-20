"""网页内容抓取器 —— 正文提取、去广告去噪。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

# HTML 标签中需要移除的噪点元素
_NOISE_TAGS: set[str] = {
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "noscript",
    "iframe",
    "form",
    "button",
}

# CSS 类名/ID 常含的广告/噪点关键词
_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"ad(s|vertisement)?", re.IGNORECASE),
    re.compile(r"banner", re.IGNORECASE),
    re.compile(r"popup", re.IGNORECASE),
    re.compile(r"sidebar", re.IGNORECASE),
    re.compile(r"comment", re.IGNORECASE),
    re.compile(r"social(-share)?", re.IGNORECASE),
    re.compile(r"breadcrumb", re.IGNORECASE),
    re.compile(r"pagination", re.IGNORECASE),
    re.compile(r"related(-articles)?", re.IGNORECASE),
]

# 正文候选标签（当无 <article> / <main> 时按优先级尝试）
_CONTENT_TAGS: list[str] = ["article", "main", '[role="main"]']

# 共享 HTTP 客户端（懒加载，连接池复用）
_http_client: httpx.AsyncClient | None = None

# 编码检测正则（Content-Type header + HTML meta charset）
_CHARSET_HEADER_RE = re.compile(r"charset=([\w-]+)", re.IGNORECASE)
_CHARSET_META_RE = re.compile(rb'<meta[^>]+charset["\']?\s*=\s*["\']?([\w-]+)', re.IGNORECASE)


def _get_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """返回共享的 httpx.AsyncClient，支持连接池复用。"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={
                "User-Agent": "ResearchAgent/0.1",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
    return _http_client


def _detect_encoding(response: httpx.Response) -> str:
    """检测响应编码，优先级：Content-Type header → HTML meta → UTF-8。"""
    # 1. 从 Content-Type header 提取 charset
    content_type = response.headers.get("content-type", "")
    if isinstance(content_type, str) and content_type:
        m = _CHARSET_HEADER_RE.search(content_type)
        if m:
            return m.group(1)

    # 2. 从 HTML meta 标签推断（扫描前 4KB）
    raw = response.content if isinstance(response.content, (bytes, bytearray)) else b""
    if raw:
        m = _CHARSET_META_RE.search(raw[:4096])
        if m:
            return m.group(1).decode("ascii", errors="ignore")

    return "utf-8"


@dataclass
class WebPage:
    """抓取结果"""

    url: str
    title: str = ""
    text: str = ""
    html: str = ""
    domain: str = ""

    @property
    def char_count(self) -> int:
        return len(self.text)


def _is_noise_element(element: Tag) -> bool:
    """判断元素是否为广告/噪点（基于 class/id/role）。"""
    # NavigableString / Comment nodes have no attrs
    attrs = getattr(element, "attrs", None)
    if attrs is None:
        return False
    class_id = " ".join(attrs.get("class", [])) + " " + attrs.get("id", "")
    for pattern in _NOISE_PATTERNS:
        if pattern.search(class_id):
            return True
    return False


def _extract_text_from_soup(soup: BeautifulSoup) -> str:
    """从 BeautifulSoup 中提取纯净正文。"""
    # 1. 移除噪点标签
    for tag in _NOISE_TAGS:
        for node in soup.find_all(tag):
            node.decompose()

    # 2. 移除含噪点 class/id 的元素
    for element in soup.find_all(True):  # all elements
        if _is_noise_element(element):
            element.decompose()

    # 3. 优先从语义化标签获取正文
    for selector in _CONTENT_TAGS:
        content = soup.select_one(selector)
        if content:
            return content.get_text(separator="\n", strip=True)

    # 4. 兜底：从 body 获取
    body = soup.body
    if body:
        return body.get_text(separator="\n", strip=True)

    return soup.get_text(separator="\n", strip=True)


def _clean_whitespace(text: str) -> str:
    """压缩多余空白行。"""
    text = re.sub(r"[\t\r]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def fetch_url(
    url: str,
    *,
    timeout: float = 30.0,
    max_length: int = 100_000,
    user_agent: str = "ResearchAgent/0.1",
) -> WebPage:
    """异步抓取并提取网页正文。

    Args:
        url: 要抓取的网页地址。
        timeout: 请求超时（秒）。
        max_length: 最大文本长度限制。
        user_agent: User-Agent 头。

    Returns:
        WebPage 含标题和纯净正文。

    Raises:
        httpx.HTTPError: 当请求失败时。
        ValueError: 当 URL 格式无效时。
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    domain = parsed.netloc
    client = _get_http_client(timeout)

    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Failed to fetch URL", url=url, domain=domain, exc_info=True)
        raise
    except Exception as exc:
        logger.error("Unexpected error fetching URL", url=url, error=str(exc))
        raise httpx.HTTPError(f"Failed to fetch {url}: {exc}") from exc

    # 编码检测：处理 GBK/GB2312 等非 UTF-8 中文网页
    response.encoding = _detect_encoding(response)
    html = response.text
    soup = BeautifulSoup(html, "lxml")

    title = ""
    title_tag = soup.title
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    text = _extract_text_from_soup(soup)
    text = _clean_whitespace(text)

    if len(text) > max_length:
        logger.info(
            "Trimming page text to max_length",
            url=url,
            original=len(text),
            max=max_length,
        )
        text = text[:max_length]

    page = WebPage(url=url, title=title, text=text, html=html, domain=domain)

    logger.info(
        "URL fetched successfully",
        url=url,
        title=title,
        char_count=page.char_count,
    )
    return page


async def fetch_multiple(
    urls: list[str],
    *,
    timeout: float = 30.0,
    max_length: int = 100_000,
    max_concurrent: int = 5,
) -> list[WebPage]:
    """并发抓取多个 URL。

    Args:
        urls: 待抓取的 URL 列表。
        timeout: 单个请求超时。
        max_length: 单页最大文本长度。
        max_concurrent: 最大并发数。

    Returns:
        WebPage 列表（部分失败的成功项也会返回）。
    """
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[WebPage] = []

    async def fetch_one(url: str) -> Optional[WebPage]:
        async with semaphore:
            try:
                return await fetch_url(url, timeout=timeout, max_length=max_length)
            except Exception:
                logger.warning("Skipping failed URL", url=url, exc_info=True)
                return None

    tasks = [fetch_one(url) for url in urls]
    gathered = await asyncio.gather(*tasks, return_exceptions=False)

    for page in gathered:
        if page is not None:
            results.append(page)

    logger.info("Batch fetch completed", total=len(urls), success=len(results))
    return results
