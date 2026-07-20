"""LLM output JSON parser with automatic repair for common formatting errors.

Handles:
- Clean JSON strings
- JSON embedded in markdown code blocks (```json ... ```)
- Trailing commas
- Single-quoted keys/values
- // and /* */ style comments
- JSON surrounded by explanatory text
"""

from __future__ import annotations

import json
import re
from typing import Any


class JSONParseError(Exception):
    """Raised when a JSON string cannot be parsed even after repair attempts."""

    def __init__(self, message: str, original_text: str = "") -> None:
        super().__init__(message)
        self.original_text = original_text


class JSONParser:
    """Parse and repair JSON output from LLM responses."""

    @staticmethod
    def parse(text: str) -> Any:
        """Parse JSON from an LLM output string, applying repairs as needed.

        Args:
            text: The raw LLM output potentially containing JSON.

        Returns:
            The parsed JSON value (dict, list, str, int, float, bool, or None).

        Raises:
            JSONParseError: If the text cannot be parsed as valid JSON.
        """
        if not isinstance(text, str) or not text.strip():
            raise JSONParseError("Input is empty or not a string", original_text=str(text))

        cleaned = JSONParser._clean_text(text)

        # Attempt direct parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Attempt repairs
        repaired = JSONParser._repair(cleaned)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise JSONParseError(
                f"Failed to parse JSON after repair: {exc}",
                original_text=text,
            ) from exc

    @staticmethod
    def _clean_text(text: str) -> str:
        """Pre-process text: extract JSON from markdown blocks and surrounding text."""
        text = text.strip()

        # Try to extract from ```json ... ``` block
        md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if md_match:
            return md_match.group(1).strip()

        # Try to extract JSON object/array from surrounding text
        # Find first { or [ and last } or ]
        obj_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if obj_match:
            return obj_match.group(1)

        return text

    @staticmethod
    def _repair(text: str) -> str:
        """Apply JSON repair transformations."""
        repaired = text

        # Remove // style comments (but preserve :// in URLs)
        repaired = JSONParser._remove_line_comments(repaired)

        # Remove /* */ style comments
        repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)

        # Remove trailing commas before ] or }
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

        # Convert single quotes to double quotes (careful with escaped quotes)
        repaired = JSONParser._fix_single_quotes(repaired)

        return repaired

    @staticmethod
    def _remove_line_comments(text: str) -> str:
        """Remove // line comments while preserving :// in URLs."""
        lines: list[str] = []
        for line in text.split("\n"):
            in_string = False
            string_char = ""
            for i, ch in enumerate(line):
                if ch in ('"', "'") and (i == 0 or line[i - 1] != "\\"):
                    if not in_string:
                        in_string = True
                        string_char = ch
                    elif ch == string_char:
                        in_string = False
                elif not in_string and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    if i == 0 or line[i - 1] != ":":
                        line = line[:i]
                        break
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _fix_single_quotes(text: str) -> str:
        """Convert single-quoted JSON keys/values to double-quoted.

        Handles the common LLM output where keys or string values use single quotes.
        Uses a state machine to avoid corrupting apostrophes inside double-quoted strings.
        """
        result: list[str] = []
        i = 0
        n = len(text)

        while i < n:
            ch = text[i]
            if ch == '"':
                # Consume double-quoted string as-is
                j = JSONParser._find_string_end(text, i, '"')
                result.append(text[i : j + 1])
                i = j + 1
            elif ch == "'":
                # Potentially a single-quoted JSON string → convert to double-quoted
                j = JSONParser._find_string_end(text, i, "'")
                inner = text[i + 1 : j]
                inner = inner.replace('\\"', '"').replace('"', '\\"')
                result.append('"' + inner + '"')
                i = j + 1
            else:
                result.append(ch)
                i += 1

        return "".join(result)

    @staticmethod
    def _find_string_end(text: str, start: int, quote_char: str) -> int:
        """Find the end index of a quoted string starting at *start*."""
        i = start + 1
        while i < len(text):
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == quote_char:
                return i
            i += 1
        return len(text) - 1
