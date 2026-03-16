"""Tests for text chunker — pure function, no external deps."""

from src.lib.chunker import ChunkWithMetadata, chunk_segments, chunk_text
from src.lib.file_parsers import ParsedSegment


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


class TestChunkSegments:
    def test_preserves_metadata(self):
        segments = [
            ParsedSegment(content="Short text", metadata={"page": 1}),
            ParsedSegment(content="Another piece", metadata={"page": 2}),
        ]
        result = chunk_segments(segments, max_chars=500)
        assert len(result) == 2
        assert result[0].content == "Short text"
        assert result[0].metadata == {"page": 1}
        assert result[1].content == "Another piece"
        assert result[1].metadata == {"page": 2}

    def test_splits_long_segment_keeps_metadata(self):
        long_content = "Line one.\n\nLine two.\n\nLine three."
        segments = [ParsedSegment(content=long_content, metadata={"slide": 3})]
        result = chunk_segments(segments, max_chars=20)
        assert len(result) >= 2
        for chunk in result:
            assert chunk.metadata == {"slide": 3}

    def test_filters_empty_segments(self):
        segments = [
            ParsedSegment(content="   ", metadata={"page": 1}),
            ParsedSegment(content="Real content", metadata={"page": 2}),
        ]
        result = chunk_segments(segments, max_chars=500)
        assert len(result) == 1
        assert result[0].content == "Real content"
        assert result[0].metadata == {"page": 2}

    def test_empty_segments_list(self):
        result = chunk_segments([], max_chars=500)
        assert result == []
