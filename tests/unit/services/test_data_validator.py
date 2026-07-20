"""Unit tests for data_validator — freshness, completeness, credibility."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from services.validators.data_validator import (  # noqa: E402
    DataValidationResult,
    check_completeness,
    check_freshness,
    score_credibility,
    validate_data,
)


class TestFreshness:
    """Verify data freshness checks."""

    def test_recent_data_is_fresh(self) -> None:
        """Data from today is fresh."""
        today = datetime.now(timezone.utc).isoformat()
        score, is_fresh = check_freshness(today)
        assert is_fresh is True
        assert score > 0.9

    def test_old_data_is_stale(self) -> None:
        """Data from 31 days ago is stale."""
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        score, is_fresh = check_freshness(old)
        assert is_fresh is False
        assert score == 0.0

    def test_boundary_30_days(self) -> None:
        """Data exactly 30 days ago is still fresh with low score."""
        boundary = (datetime.now(timezone.utc) - timedelta(days=29, hours=23, minutes=59, seconds=59)).isoformat()
        score, is_fresh = check_freshness(boundary)
        assert is_fresh is True
        assert score == pytest.approx(0.2, abs=0.01)

    def test_none_timestamp(self) -> None:
        """None timestamp returns stale."""
        score, is_fresh = check_freshness(None)
        assert is_fresh is False
        assert score == 0.0

    def test_invalid_timestamp(self) -> None:
        """Invalid timestamp string returns stale."""
        score, is_fresh = check_freshness("not-a-date")
        assert is_fresh is False

    def test_future_date_is_stale(self) -> None:
        """Future dates are rejected."""
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        score, is_fresh = check_freshness(future)
        assert is_fresh is False

    def test_custom_max_age(self) -> None:
        """Custom max_age_days works."""
        today = datetime.now(timezone.utc).isoformat()
        score, is_fresh = check_freshness(today, max_age_days=1)
        assert is_fresh is True

    def test_naive_datetime_treated_as_utc(self) -> None:
        """Naive datetime is treated as UTC."""
        dt = datetime.now() - timedelta(days=2)
        score, is_fresh = check_freshness(dt.isoformat())
        assert is_fresh is True


class TestCompleteness:
    """Verify data completeness checks."""

    def test_fully_complete(self) -> None:
        """All required fields present."""
        data = {"title": "T", "url": "https://x.com", "content": "C", "source": "S"}
        score, missing = check_completeness(data)
        assert score == 1.0
        assert missing == []

    def test_partial_completeness(self) -> None:
        """Some fields missing."""
        data = {"title": "T", "content": "C"}
        score, missing = check_completeness(data)
        assert score == 0.5
        assert "url" in missing
        assert "source" in missing

    def test_empty_string_counts_as_missing(self) -> None:
        """Empty strings are treated as missing."""
        data = {"title": "", "url": "https://x.com", "content": "C", "source": " "}
        score, missing = check_completeness(data)
        assert score == 0.5
        assert "title" in missing
        assert "source" in missing

    def test_all_missing(self) -> None:
        """All fields missing."""
        score, missing = check_completeness({})
        assert score == 0.0
        assert len(missing) == 4


class TestCredibility:
    """Verify source credibility scoring."""

    def test_high_credibility_domains(self) -> None:
        """Government / major institutional domains score high."""
        assert score_credibility("https://stats.gov.cn/data/report") == 1.0
        assert score_credibility("https://www.imf.org/publications") == 1.0
        assert score_credibility("https://bloomberg.com/news/article") == 1.0

    def test_subdomain_of_trusted(self) -> None:
        """Subdomains of trusted domains score 0.9."""
        assert score_credibility("https://data.stats.gov.cn/report") == 0.9

    def test_medium_credibility(self) -> None:
        """Medium-credibility domains score 0.5."""
        assert score_credibility("https://36kr.com/news") == 0.5
        assert score_credibility("https://www.zhihu.com/question") == 0.5

    def test_unknown_domain(self) -> None:
        """Unknown domains score 0.0."""
        assert score_credibility("https://random-blog.example.com/post") == 0.0

    def test_none_url(self) -> None:
        """None URL scores 0.0."""
        assert score_credibility(None) == 0.0

    def test_gov_domain_generic(self) -> None:
        """Any .gov.* domain scores 0.8."""
        assert score_credibility("https://example.gov.br/report") == 0.8

    def test_edu_domain(self) -> None:
        """.edu domains score 0.7."""
        assert score_credibility("https://csail.mit.edu/paper") == 0.7

    def test_domain_with_port_ignored(self) -> None:
        """Port numbers in URL are ignored."""
        assert score_credibility("https://stats.gov.cn:443/report") == 1.0


class TestValidateData:
    """Verify combined data validation."""

    def test_perfect_data(self) -> None:
        """Fresh, complete, high-credibility data passes."""
        record = {
            "title": "T",
            "url": "https://stats.gov.cn/r",
            "content": "C",
            "source": "https://stats.gov.cn/r",
        }
        result = validate_data(record, collected_at=datetime.now(timezone.utc).isoformat())
        assert result.is_valid is True
        assert result.freshness_score > 0.9
        assert result.completeness_score == 1.0
        assert result.credibility_score == 1.0

    def test_stale_and_incomplete_data(self) -> None:
        """Stale incomplete data fails."""
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        record = {"title": "T"}
        result = validate_data(record, collected_at=old)
        assert result.is_valid is False
        assert len(result.errors) >= 2

    def test_low_credibility_warning(self) -> None:
        """Low credibility source adds warnings."""
        record = {
            "title": "T",
            "url": "https://blog.com/p",
            "content": "C",
            "source": "https://blog.com/p",
        }
        result = validate_data(record, collected_at=datetime.now(timezone.utc).isoformat())
        assert result.credibility_score == 0.0
        assert len(result.warnings) >= 1
