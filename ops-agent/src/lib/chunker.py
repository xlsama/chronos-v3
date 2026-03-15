import re


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
