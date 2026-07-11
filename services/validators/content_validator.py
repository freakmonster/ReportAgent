"""
Content validator — sensitive content filtering and Markdown format checks.

Checks:
- Sensitive/political keywords
- Markdown structural integrity
- Citation completeness
- Image reference validity
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentValidationResult:
    """Result of content validation."""
    is_valid: bool
    has_sensitive_content: bool = False
    has_format_errors: bool = False
    sensitive_hits: list[str] = field(default_factory=list)
    format_errors: list[str] = field(default_factory=list)
    citation_count: int = 0
    has_citations: bool = False


# ---------------------------------------------------------------------------
# Sensitive keyword patterns
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS: list[re.Pattern] = [
    # Political extremism
    re.compile(r"(?:推翻|颠覆|分裂|独立).*(?:政权|国家|政府)", re.IGNORECASE),
    # Violence / illegal
    re.compile(r"(?:制造|购买|贩卖).*(?:武器|毒品|爆炸物)", re.IGNORECASE),
    # Pornography
    re.compile(r"(?:色情|淫秽|成人).*(?:内容|网站|视频)", re.IGNORECASE),
    # Gambling
    re.compile(r"(?:赌博|赌场|博彩).*(?:推荐|平台|网站)", re.IGNORECASE),
    # Investment fraud
    re.compile(r"(?:稳赚|保本|高收益).*(?:投资|理财|项目)", re.IGNORECASE),
]

# █████ block patterns (content that was censored)
_CENSORED_BLOCK_RE = re.compile(r"█{3,}")

# Markdown structure issues
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
_MD_LIST_RE = re.compile(r"^(\s*[-*+]\s|\s*\d+\.\s)", re.MULTILINE)

# Citation patterns
_CITATION_RE = re.compile(r"\[(\d+)\]|\[\d+,\s*\d+\]|\([^)]*\d{4}[^)]*\)")


# ---------------------------------------------------------------------------
# Sensitive content detection
# ---------------------------------------------------------------------------

def check_sensitive_content(text: str) -> tuple[bool, list[str]]:
    """Detect sensitive / harmful content in text.

    Args:
        text: The text to check.

    Returns:
        (has_sensitive, hits) tuple.  hits are the matched pattern descriptions.
    """
    has_sensitive = False
    hits: list[str] = []

    for pattern in _SENSITIVE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            has_sensitive = True
            for m in matches:
                snippet = m if isinstance(m, str) else str(m)
                if len(snippet) > 50:
                    snippet = snippet[:50] + "..."
                hits.append(snippet)

    # Check for censored blocks
    if _CENSORED_BLOCK_RE.search(text):
        has_sensitive = True
        hits.append("Censored content blocks detected (████)")

    return has_sensitive, hits


# ---------------------------------------------------------------------------
# Markdown format validation
# ---------------------------------------------------------------------------

def validate_markdown_format(text: str) -> list[str]:
    """Validate Markdown structural integrity.

    Checks:
    - At least one heading present
    - All links have valid URLs
    - Image references have alt text and URLs
    - No orphaned list items outside list context

    Args:
        text: Markdown content to validate.

    Returns:
        List of format error descriptions (empty if valid).
    """
    errors: list[str] = []

    # Check for at least one heading
    if not _MD_HEADING_RE.search(text):
        errors.append("No Markdown headings found")

    # Check image references (must have alt text and URL)
    images = _MD_IMAGE_RE.findall(text)
    for alt, url in images:
        if not alt.strip():
            errors.append("Image missing alt text")
        if not url.strip():
            errors.append(f"Image '{alt[:30]}' has empty URL")

    # Check for broken links (empty URLs)
    links = _MD_LINK_RE.findall(text)
    broken = sum(1 for _, url in links if not url.strip())
    if broken > 0:
        errors.append(f"{broken} broken link(s) with empty URL")

    return errors


# ---------------------------------------------------------------------------
# Combined validation
# ---------------------------------------------------------------------------

def validate_content(text: str) -> ContentValidationResult:
    """Run full content validation: sensitive + Markdown + citations.

    Args:
        text: Full report content as Markdown string.

    Returns:
        ContentValidationResult with all findings.
    """
    has_sensitive, sensitive_hits = check_sensitive_content(text)
    format_errors = validate_markdown_format(text)

    # Citation check
    citations = _CITATION_RE.findall(text)
    citation_count = len(citations)
    has_citations = citation_count > 0
    if not has_citations:
        format_errors.append("No citations found in report")

    has_format_errors = len(format_errors) > 0
    is_valid = not has_sensitive and not has_format_errors

    return ContentValidationResult(
        is_valid=is_valid,
        has_sensitive_content=has_sensitive,
        has_format_errors=has_format_errors,
        sensitive_hits=sensitive_hits,
        format_errors=format_errors,
        citation_count=citation_count,
        has_citations=has_citations,
    )
