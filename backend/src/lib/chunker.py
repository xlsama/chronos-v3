from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.lib.file_parsers import ParsedSegment


@dataclass
class ChunkWithMetadata:
    content: str
    metadata: dict = field(default_factory=dict)


def chunk_segments(segments: list[ParsedSegment], max_chars: int = 500) -> list[ChunkWithMetadata]:
    """Chunk each segment and propagate its metadata to sub-chunks."""
    result: list[ChunkWithMetadata] = []
    for seg in segments:
        chunks = chunk_text(seg.content, max_chars)
        for chunk in chunks:
            result.append(ChunkWithMetadata(content=chunk, metadata=seg.metadata))
    return result


def chunk_text(text: str, max_chars: int = 500) -> list[str]:
    if not text or not text.strip():
        return []

    # Split by markdown headers or double newlines
    segments = re.split(r"\n(?=#{1,6}\s)|\n\n+", text)

    chunks: list[str] = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        if len(segment) <= max_chars:
            chunks.append(segment)
        else:
            # Split long segments by lines
            _split_long_segment(segment, max_chars, chunks)

    return chunks


def _split_long_segment(segment: str, max_chars: int, chunks: list[str]) -> None:
    lines = segment.split("\n")
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = line[:max_chars] if len(line) > max_chars else line
    if current.strip():
        chunks.append(current)
