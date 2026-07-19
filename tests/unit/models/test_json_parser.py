"""Unit tests for JSONParser and RetryParser — JSON repair and retry logic."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is importable — multiple strategies for robustness
_project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
# Fallback: also add using absolute path
_abs_root = r"e:\wokr\Agent\multiAgent"
if _abs_root not in sys.path:
    sys.path.insert(0, _abs_root)

import pytest  # noqa: E402

from models.parsers.json_parser import JSONParseError, JSONParser  # noqa: E402
from models.parsers.retry_parser import RetryExhaustedError, RetryParser  # noqa: E402

# ── JSONParser tests ──────────────────────────────────────────────────


class TestJSONParser:
    """Tests for JSONParser.parse()."""

    def test_parse_valid_json(self) -> None:
        """Verify clean JSON parses correctly."""
        result = JSONParser.parse('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_parse_json_array(self) -> None:
        """Verify JSON arrays parse correctly."""
        result = JSONParser.parse('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_parse_json_in_markdown_block(self) -> None:
        """Verify JSON inside ```json ... ``` block is extracted and parsed."""
        text = """Here is the result:
```json
{"status": "ok", "items": [1, 2, 3]}
```
That's all."""
        result = JSONParser.parse(text)
        assert result == {"status": "ok", "items": [1, 2, 3]}

    def test_parse_json_in_markdown_block_no_lang(self) -> None:
        """Verify JSON inside ``` ... ``` block without language specifier."""
        text = '```\n{"a": 1}\n```'
        result = JSONParser.parse(text)
        assert result == {"a": 1}

    def test_parse_json_with_trailing_comma(self) -> None:
        """Verify trailing comma is removed and JSON parsed."""
        text = '{"name": "Alice", "age": 30,}'
        result = JSONParser.parse(text)
        assert result == {"name": "Alice", "age": 30}

    def test_parse_json_with_trailing_comma_in_array(self) -> None:
        """Verify trailing comma in array is removed."""
        text = '[1, 2, 3,]'
        result = JSONParser.parse(text)
        assert result == [1, 2, 3]

    def test_parse_json_with_single_quotes(self) -> None:
        """Verify single-quoted JSON is converted to double quotes and parsed."""
        text = "{'key': 'value', 'num': 42}"
        result = JSONParser.parse(text)
        assert result == {"key": "value", "num": 42}

    def test_parse_json_with_line_comments(self) -> None:
        """Verify // comments are stripped."""
        text = """{
            "name": "Alice",  // User's name
            "age": 30  // User's age
        }"""
        result = JSONParser.parse(text)
        assert result == {"name": "Alice", "age": 30}

    def test_parse_json_with_block_comments(self) -> None:
        """Verify /* */ comments are stripped."""
        text = """{
            "name": "Alice",
            /* This is a block comment */
            "age": 30
        }"""
        result = JSONParser.parse(text)
        assert result == {"name": "Alice", "age": 30}

    def test_parse_json_with_text_surrounding(self) -> None:
        """Verify JSON is extracted from surrounding explanatory text."""
        text = "The answer is: {\"result\": \"success\"}. That's correct."
        result = JSONParser.parse(text)
        assert result == {"result": "success"}

    def test_parse_nested_json(self) -> None:
        """Verify nested JSON objects parse correctly."""
        text = '{"user": {"name": "Alice", "roles": ["admin", "editor"]}}'
        result = JSONParser.parse(text)
        assert result["user"]["name"] == "Alice"
        assert "admin" in result["user"]["roles"]

    def test_parse_invalid_json_raises(self) -> None:
        """Verify completely invalid text raises JSONParseError."""
        with pytest.raises(JSONParseError):
            JSONParser.parse("This is just a plain text, not JSON at all.")

    def test_parse_empty_input_raises(self) -> None:
        """Verify empty input raises JSONParseError."""
        with pytest.raises(JSONParseError, match="empty"):
            JSONParser.parse("")

    def test_parse_whitespace_only_raises(self) -> None:
        """Verify whitespace-only input raises JSONParseError."""
        with pytest.raises(JSONParseError, match="empty"):
            JSONParser.parse("   \n\t  ")

    def test_parse_non_string_raises(self) -> None:
        """Verify non-string input raises JSONParseError."""
        with pytest.raises(JSONParseError, match="empty"):
            JSONParser.parse(None)  # type: ignore[arg-type]


# ── RetryParser tests ─────────────────────────────────────────────────


class TestRetryParser:
    """Tests for RetryParser.retry_parse()."""

    def test_retry_succeeds_on_second_attempt(self) -> None:
        """Verify that repair callback fixes JSON on second attempt."""
        parser = RetryParser(max_retries=3)
        # Use text that always fails even after auto-repair
        bad_json = "not valid json at all {{{{"

        call_count = {"count": 0}

        def repair_callback(text: str) -> str:
            call_count["count"] += 1
            if call_count["count"] == 1:
                # First repair: return valid JSON
                return '{"result": "ok"}'
            return text

        result = parser.retry_parse(bad_json, repair_callback=repair_callback)

        assert result == {"result": "ok"}
        assert call_count["count"] >= 1  # At least one repair call

    def test_retry_succeeds_first_try(self) -> None:
        """Verify valid JSON succeeds on first attempt without calling repair."""
        parser = RetryParser(max_retries=3)
        valid_json = '{"key": "value"}'

        repair_called = MagicMock(return_value="should not be called")

        result = parser.retry_parse(valid_json, repair_callback=repair_called)

        assert result == {"key": "value"}
        repair_called.assert_not_called()

    def test_retry_exhausted_raises(self) -> None:
        """Verify RetryExhaustedError when all attempts fail."""
        parser = RetryParser(max_retries=3)
        invalid_json = "not json at all, completely broken"

        # Repair callback that doesn't help
        def bad_repair(text: str) -> str:
            return text + " (still broken)"

        with pytest.raises(RetryExhaustedError) as exc_info:
            parser.retry_parse(invalid_json, repair_callback=bad_repair)

        assert "Failed to parse JSON after 3 attempts" in str(exc_info.value)
        assert exc_info.value.original_text == invalid_json

    def test_retry_exhausted_without_callback_raises(self) -> None:
        """Verify RetryExhaustedError on first attempt without repair callback."""
        parser = RetryParser(max_retries=2)
        invalid_json = "still not json"

        with pytest.raises(RetryExhaustedError) as exc_info:
            parser.retry_parse(invalid_json)

        assert "no repair callback" in str(exc_info.value)

    def test_retry_repair_callback_exception_handled(self) -> None:
        """Verify that if repair callback itself raises, retry continues gracefully."""
        parser = RetryParser(max_retries=2)

        def failing_repair(text: str) -> str:
            raise RuntimeError("repair tool crash")

        with pytest.raises(RetryExhaustedError):
            parser.retry_parse("bad json", repair_callback=failing_repair)

    def test_retry_uses_custom_max_retries(self) -> None:
        """Verify custom max_retries configuration is respected."""
        parser = RetryParser(max_retries=5)
        assert parser._max_retries == 5

        invalid_json = "not json"

        def fake_repair(text: str) -> str:
            return text + " (repaired)"

        with pytest.raises(RetryExhaustedError) as exc_info:
            parser.retry_parse(invalid_json, repair_callback=fake_repair)

        assert "5 attempts" in str(exc_info.value)
