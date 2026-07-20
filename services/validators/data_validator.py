"""
Data validator — freshness, completeness, source credibility scoring.

Checks:
- Data freshness: not older than 30 days
- Data completeness: required fields present
- Source credibility: domain-based trust scoring
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Maximum allowed data age in days
MAX_AGE_DAYS: int = 30

# High-credibility domains (whitelist)
_HIGH_CREDIBILITY_DOMAINS: set[str] = {
    "gov.cn",
    "stats.gov.cn",
    "pbc.gov.cn",
    "csrc.gov.cn",
    "who.int",
    "worldbank.org",
    "imf.org",
    "un.org",
    "bloomberg.com",
    "reuters.com",
    "ft.com",
    "wsj.com",
    "caixin.com",
    "cls.cn",
    "eastmoney.com",
    "sse.com.cn",
    "szse.cn",
    "sec.gov",
    "chinamoney.com.cn",
    "cctv.com",
    "people.com.cn",
    "xinhuanet.com",
    "sciencedirect.com",
    "nature.com",
    "ieee.org",
    "cnki.net",
    "wanfangdata.com.cn",
}

# Medium-credibility domains
_MEDIUM_CREDIBILITY_DOMAINS: set[str] = {
    "163.com",
    "qq.com",
    "sina.com.cn",
    "sohu.com",
    "36kr.com",
    "jiemian.com",
    "thepaper.cn",
    "baidu.com",
    "zhihu.com",
    "weixin.qq.com",
    "wikipedia.org",
    "medium.com",
}

# Required fields for a valid data point
_REQUIRED_DATA_FIELDS: set[str] = {
    "title",
    "url",
    "content",
    "source",
}


@dataclass
class DataValidationResult:
    """Result of data validation."""

    is_valid: bool
    freshness_score: float  # 0.0 - 1.0 (1.0 = very fresh)
    completeness_score: float  # 0.0 - 1.0
    credibility_score: float  # 0.0 - 1.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------


def check_freshness(
    collected_at: str | None = None,
    max_age_days: int = MAX_AGE_DAYS,
) -> tuple[float, bool]:
    """Check how fresh the collected data is.

    Args:
        collected_at: ISO-format datetime string of when data was collected.
        max_age_days: Maximum acceptable age in days.

    Returns:
        (score, is_fresh) tuple.  score=1.0 means collected today,
        score=0.0 means unknown or too old.
    """
    if collected_at is None:
        return 0.0, False

    try:
        dt = datetime.fromisoformat(collected_at)
    except (ValueError, TypeError):
        return 0.0, False

    now = datetime.now(timezone.utc)
    # Make naive datetime aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    age = (now - dt).total_seconds() / 86400  # days
    if age < 0:
        return 0.0, False  # future date

    if age <= max_age_days:
        score = 1.0 - (age / max_age_days) * 0.8  # 1.0 → 0.2 over 30 days
        return round(max(score, 0.0), 2), True

    return 0.0, False


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def check_completeness(data: dict[str, Any]) -> tuple[float, list[str]]:
    """Check how complete a data record is.

    Args:
        data: Dict with at least title, url, content, source fields.

    Returns:
        (score, missing_fields) tuple.  score=1.0 means all fields present.
    """
    missing: list[str] = []
    for fname in _REQUIRED_DATA_FIELDS:
        val = data.get(fname)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(fname)

    if not missing:
        return 1.0, []

    score = 1.0 - len(missing) / len(_REQUIRED_DATA_FIELDS)
    return round(score, 2), missing


# ---------------------------------------------------------------------------
# Credibility
# ---------------------------------------------------------------------------


def score_credibility(source_url: str | None) -> float:
    """Score the credibility of a source based on its domain.

    Args:
        source_url: Full URL of the source.

    Returns:
        Score from 0.0 (unknown/untrusted) to 1.0 (highly trusted).
    """
    if not source_url:
        return 0.0

    domain = _extract_domain(source_url)
    if not domain:
        return 0.0

    # Exact match
    if domain in _HIGH_CREDIBILITY_DOMAINS:
        return 1.0

    # Check if it's a subdomain of a trusted domain
    for trusted in _HIGH_CREDIBILITY_DOMAINS:
        if domain.endswith("." + trusted):
            return 0.9

    if domain in _MEDIUM_CREDIBILITY_DOMAINS:
        return 0.5

    for medium in _MEDIUM_CREDIBILITY_DOMAINS:
        if domain.endswith("." + medium):
            return 0.4

    # Government domains (.gov.*)
    if ".gov." in domain:
        return 0.8

    # Educational domains
    if domain.endswith(".edu") or ".edu." in domain:
        return 0.7

    return 0.0


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL.

    Args:
        url: Full URL string.

    Returns:
        Lowercase domain (e.g., 'stats.gov.cn') or empty string.
    """
    url = url.strip().lower()
    # Remove protocol
    if "://" in url:
        url = url.split("://", 1)[1]
    # Remove path/query
    if "/" in url:
        url = url.split("/", 1)[0]
    # Remove port
    if ":" in url and url.split(":")[-1].isdigit():
        url = url.rsplit(":", 1)[0]
    # Remove leading www.
    if url.startswith("www."):
        url = url[4:]
    return url


# ---------------------------------------------------------------------------
# Combined validation
# ---------------------------------------------------------------------------


def validate_data(
    record: dict[str, Any],
    collected_at: str | None = None,
    max_age_days: int = MAX_AGE_DAYS,
) -> DataValidationResult:
    """Run full data validation: freshness + completeness + credibility.

    Args:
        record: Dict with title, url, content, source fields.
        collected_at: ISO datetime of data collection.
        max_age_days: Max acceptable age.

    Returns:
        DataValidationResult with scores and issues.
    """
    errors: list[str] = []
    warnings: list[str] = []

    freshness, is_fresh = check_freshness(collected_at, max_age_days)
    if not is_fresh:
        if collected_at:
            errors.append(f"Data is too old (collected: {collected_at})")
        else:
            warnings.append("Data collection timestamp is unknown; assuming stale")

    completeness, missing = check_completeness(record)
    if missing:
        errors.append(f"Missing fields: {', '.join(missing)}")

    source_url = record.get("source", record.get("url", ""))
    credibility = score_credibility(source_url if isinstance(source_url, str) else "")

    if credibility < 0.3:
        warnings.append(f"Low source credibility ({credibility:.0%}) for {source_url}")

    is_valid = len(errors) == 0 and is_fresh and completeness == 1.0

    return DataValidationResult(
        is_valid=is_valid,
        freshness_score=freshness,
        completeness_score=completeness,
        credibility_score=credibility,
        errors=errors,
        warnings=warnings,
    )
