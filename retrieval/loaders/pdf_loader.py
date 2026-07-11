"""PDF 文档解析器 —— 流式解析，单文件最大 200 页限制，超限引导报错。"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Iterator, Optional

from infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

MAX_PAGES: int = 200


@dataclass
class PDFPage:
    """单页结果"""
    page_num: int
    text: str


@dataclass
class PDFDocument:
    """解析后的 PDF 文档"""
    source: str
    total_pages: int
    pages: list[PDFPage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)


def parse_pdf(
    source: str,
    content: bytes,
    *,
    max_pages: int = MAX_PAGES,
    first_page: int = 1,
) -> PDFDocument:
    """使用 pypdf 解析 PDF 为 PDFDocument 对象。

    Args:
        source: 文档来源标识 (URL 或文件路径)。
        content: PDF 文件的原始字节。
        max_pages: 最大页数限制，超限抛异常。
        first_page: 起始页码（用于增量解析）。

    Returns:
        PDFDocument 含所有已解析页。

    Raises:
        ValueError: 当 PDF 页数超过 max_pages 时。
        RuntimeError: 当 PDF 损坏或无法读取时。
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required for PDF loading. Install with: pip install pypdf")

    if not content:
        raise ValueError("Empty PDF content provided")

    stream = io.BytesIO(content)
    try:
        reader = PdfReader(stream)
    except Exception as exc:
        logger.error("Failed to open PDF", source=source, error=str(exc))
        raise RuntimeError(f"Failed to read PDF from {source}: {exc}") from exc

    total_pages = len(reader.pages)

    if total_pages > max_pages:
        msg = (
            f"PDF has {total_pages} pages, exceeds the maximum of {max_pages} pages. "
            f"Please split the document into smaller parts or use a different source."
        )
        logger.warning("PDF page limit exceeded", source=source, pages=total_pages, max=max_pages)
        raise ValueError(msg)

    doc = PDFDocument(source=source, total_pages=total_pages)

    for idx, page in enumerate(reader.pages):
        page_num = first_page + idx
        text = page.extract_text() or ""
        doc.pages.append(PDFPage(page_num=page_num, text=text.strip()))

    logger.info(
        "PDF parsed successfully",
        source=source,
        pages=total_pages,
        char_count=len(doc.full_text),
    )
    return doc


def parse_pdf_streaming(
    source: str,
    content: bytes,
    *,
    max_pages: int = MAX_PAGES,
    batch_size: int = 10,
) -> Iterator[list[PDFPage]]:
    """流式解析 PDF，按批次 yield 页面。

    适用于内存受限场景——每次只保持 batch_size 个页面在内存中。

    Args:
        source: 文档来源标识。
        content: PDF 文件的原始字节。
        max_pages: 最大页数限制。
        batch_size: 每批次返回的页数。

    Yields:
        list[PDFPage]: 每批次 max batch_size 页。

    Raises:
        ValueError: 当 PDF 页数超过 max_pages 时。
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required for PDF loading. Install with: pip install pypdf")

    if not content:
        raise ValueError("Empty PDF content provided")

    stream = io.BytesIO(content)
    reader: Any = None
    try:
        reader = PdfReader(stream)
        total_pages = len(reader.pages)

        if total_pages > max_pages:
            msg = (
                f"PDF has {total_pages} pages, exceeds the maximum of {max_pages} pages. "
                f"Please split the document into smaller parts or use a different source."
            )
            logger.warning("PDF page limit exceeded", source=source, pages=total_pages, max=max_pages)
            raise ValueError(msg)

        batch: list[PDFPage] = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            batch.append(PDFPage(page_num=idx + 1, text=text.strip()))

            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:
            yield batch

        logger.info(
            "PDF streamed successfully",
            source=source,
            pages=total_pages,
        )
    finally:
        # 释放 PdfReader 内部的流引用，帮助 GC 更快回收 BytesIO
        if reader is not None:
            reader.stream.close()
        stream.close()


def count_pages(content: bytes) -> int:
    """快速获取 PDF 页数（不提取文本）。

    用于在解析前判断是否需要拆分。

    Args:
        content: PDF 文件的原始字节。

    Returns:
        总页数。
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required for PDF loading. Install with: pip install pypdf")
    return len(PdfReader(io.BytesIO(content)).pages)
