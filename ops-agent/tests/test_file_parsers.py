"""Tests for file parsers."""

import pytest

from src.lib.file_parsers import parse_csv, parse_file, parse_text, SUPPORTED_EXTENSIONS


class TestParseText:
    def test_parses_utf8(self):
        content = "Hello, world!".encode("utf-8")
        assert parse_text(content) == "Hello, world!"

    def test_handles_non_utf8(self):
        content = b"\xff\xfe"
        result = parse_text(content)
        assert isinstance(result, str)


class TestParseCsv:
    def test_parses_simple_csv(self):
        content = "name,age\nAlice,30\nBob,25".encode("utf-8")
        result = parse_csv(content)
        assert "name" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "|" in result  # markdown table format

    def test_empty_csv(self):
        content = b""
        assert parse_csv(content) == ""


class TestParseFile:
    def test_text_file(self):
        content = b"Hello text"
        assert parse_file(content, "readme.txt") == "Hello text"

    def test_markdown_file(self):
        content = b"# Title"
        assert parse_file(content, "readme.md") == "# Title"

    def test_csv_file(self):
        content = b"a,b\n1,2"
        result = parse_file(content, "data.csv")
        assert "a" in result
        assert "1" in result

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported"):
            parse_file(b"data", "file.xyz")


class TestSupportedExtensions:
    def test_has_common_formats(self):
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".xlsx" in SUPPORTED_EXTENSIONS
        assert ".csv" in SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
