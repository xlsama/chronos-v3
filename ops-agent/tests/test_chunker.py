"""Tests for text chunker — pure function, no external deps."""

from src.lib.chunker import chunk_text


class TestChunkText:
    def test_short_text_single_chunk(self):
        result = chunk_text("Hello world")
        assert result == ["Hello world"]

    def test_split_by_double_newline(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = chunk_text(text, max_chars=500)
        assert len(result) == 3
        assert result[0] == "Paragraph one."
        assert result[1] == "Paragraph two."
        assert result[2] == "Paragraph three."

    def test_split_by_markdown_header(self):
        text = "# Header 1\nContent one.\n\n## Header 2\nContent two."
        result = chunk_text(text, max_chars=500)
        assert len(result) == 2
        assert result[0].startswith("# Header 1")
        assert result[1].startswith("## Header 2")

    def test_long_paragraph_split_by_lines(self):
        lines = [f"Line {i} with some text content." for i in range(50)]
        text = "\n".join(lines)
        result = chunk_text(text, max_chars=200)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 200

    def test_empty_paragraphs_filtered(self):
        text = "Hello.\n\n\n\nWorld."
        result = chunk_text(text, max_chars=500)
        assert result == ["Hello.", "World."]

    def test_order_preserved(self):
        text = "First.\n\nSecond.\n\nThird."
        result = chunk_text(text, max_chars=500)
        assert result == ["First.", "Second.", "Third."]

    def test_empty_text_returns_empty(self):
        result = chunk_text("")
        assert result == []

    def test_whitespace_only_returns_empty(self):
        result = chunk_text("   \n\n   ")
        assert result == []
