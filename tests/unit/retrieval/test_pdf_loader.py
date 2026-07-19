"""Unit tests for pdf_loader — streaming parse, page limit, error guidance."""

import pytest

from retrieval.loaders.pdf_loader import (
    MAX_PAGES,
    PDFDocument,
    count_pages,
    parse_pdf,
    parse_pdf_streaming,
)

# A minimal valid 1-page PDF
_MIN_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n183\n%%EOF"
)


def _make_pdf(page_count: int) -> bytes:
    """Generate a simple multi-page PDF with minimal overhead."""
    pages_obj = []
    kids_refs = []
    for i in range(page_count):
        obj_num = 3 + i
        pages_obj.append(
            f"{obj_num} 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        )
        kids_refs.append(f"{obj_num} 0 R")

    catalog = "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    pages_root = (
        f"2 0 obj<</Type/Pages/Kids[{' '.join(kids_refs)}]/Count {page_count}>>endobj\n"
    )
    body = "\n".join(pages_obj)

    xref_entries = [
        "0000000000 65535 f ",
        "0000000009 00000 n ",
        "0000000058 00000 n ",
    ]
    offset = 115
    for _ in range(page_count):
        xref_entries.append(f"{offset:010d} 00000 n ")
        offset += 80

    xref = f"xref\n0 {3 + page_count}\n" + "\n".join(xref_entries)
    trailer = f"trailer<</Size {3 + page_count}/Root 1 0 R>>\nstartxref\n{offset}\n%%EOF"

    full = f"%PDF-1.4\n{catalog}{pages_root}{body}\n{xref}\n{trailer}"
    return full.encode("ascii")


class TestParsePDF:
    def test_minimal_pdf(self):
        doc = parse_pdf("test.pdf", _MIN_PDF_BYTES)
        assert isinstance(doc, PDFDocument)
        assert doc.source == "test.pdf"
        assert doc.total_pages == 1

    def test_streaming_batch(self):
        pdf = _make_pdf(25)
        batches = list(parse_pdf_streaming("test.pdf", pdf, batch_size=10))
        assert len(batches) == 3  # 10 + 10 + 5
        assert len(batches[0]) == 10
        assert len(batches[2]) == 5

    def test_exceeds_max_pages(self):
        pdf = _make_pdf(201)
        with pytest.raises(ValueError, match="exceeds the maximum"):
            parse_pdf("large.pdf", pdf)

    def test_empty_content(self):
        with pytest.raises(ValueError, match="Empty PDF content"):
            parse_pdf("empty.pdf", b"")

    def test_count_pages(self):
        assert count_pages(_MIN_PDF_BYTES) == 1
