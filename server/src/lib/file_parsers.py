"""File parsers for extracting text from various document formats."""

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docling_core.types.doc import DoclingDocument


@dataclass
class ParsedSegment:
    content: str
    metadata: dict = field(default_factory=dict)


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Formats handled by docling
DOCLING_FORMATS = {".pdf", ".docx", ".pptx", ".xlsx", ".xls"}


def is_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# Docling converter (lazy singleton)
# ---------------------------------------------------------------------------
_converter = None


def _get_converter():
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter

        _converter = DocumentConverter()
    return _converter


def _convert_bytes(file_bytes: bytes, filename: str) -> "DoclingDocument":
    """Convert file bytes to a DoclingDocument using docling."""
    from docling.datamodel.base_models import DocumentStream

    stream = DocumentStream(name=filename, stream=io.BytesIO(file_bytes))
    result = _get_converter().convert(source=stream)
    return result.document


# ---------------------------------------------------------------------------
# Docling-based segment extractors
# ---------------------------------------------------------------------------
def _pdf_segments(doc: "DoclingDocument") -> list[ParsedSegment]:
    """Extract one segment per PDF page."""
    segments = []
    for page_no in sorted(doc.pages.keys()):
        md = doc.export_to_markdown(page_no=page_no)
        if md.strip():
            segments.append(ParsedSegment(content=md, metadata={"page": page_no}))
    return segments


def _pptx_segments(doc: "DoclingDocument") -> list[ParsedSegment]:
    """Extract one segment per PPTX slide."""
    segments = []
    for page_no in sorted(doc.pages.keys()):
        md = doc.export_to_markdown(page_no=page_no)
        if md.strip():
            segments.append(ParsedSegment(
                content=f"### Slide {page_no}\n\n{md}",
                metadata={"slide": page_no},
            ))
    return segments


def _xlsx_segments(doc: "DoclingDocument") -> list[ParsedSegment]:
    """Extract one segment per Excel sheet (docling maps sheets to pages)."""
    segments = []
    for page_no in sorted(doc.pages.keys()):
        md = doc.export_to_markdown(page_no=page_no)
        if md.strip():
            segments.append(ParsedSegment(
                content=f"### Sheet {page_no}\n\n{md}",
                metadata={"sheet": page_no},
            ))
    return segments


def parse_docling_segments(file_bytes: bytes, filename: str) -> list[ParsedSegment]:
    """Parse a document using docling, returning per-page/slide/sheet segments."""
    doc = _convert_bytes(file_bytes, filename)
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        segments = _pdf_segments(doc)
    elif ext == ".pptx":
        segments = _pptx_segments(doc)
    elif ext in (".xlsx", ".xls"):
        segments = _xlsx_segments(doc)
    else:
        # .docx — single segment
        md = doc.export_to_markdown()
        segments = [ParsedSegment(content=md)] if md.strip() else []

    return segments


def parse_docling(file_bytes: bytes, filename: str = "") -> str:
    """Parse a document using docling, returning full markdown text."""
    segments = parse_docling_segments(file_bytes, filename)
    return "\n\n".join(seg.content for seg in segments)


# ---------------------------------------------------------------------------
# Simple text-based parsers (unchanged)
# ---------------------------------------------------------------------------
def parse_text(file_bytes: bytes, _filename: str = "") -> str:
    """Parse plain text / markdown files."""
    return file_bytes.decode("utf-8", errors="replace")


def parse_csv(file_bytes: bytes, _filename: str = "") -> str:
    """Parse CSV files into a readable text table."""
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return ""
    # Format as markdown table
    header = rows[0]
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows[1:]:
        # Pad row to match header length
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[:len(header)]) + " |")
    return "\n".join(lines)


def parse_html(file_bytes: bytes, _filename: str = "") -> str:
    """Parse HTML files using BeautifulSoup."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(file_bytes, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def parse_json(file_bytes: bytes, _filename: str = "") -> str:
    """Parse JSON files into formatted text."""
    text = file_bytes.decode("utf-8", errors="replace")
    data = json.loads(text)
    return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Extension → parser mappings
# ---------------------------------------------------------------------------
PARSERS = {
    ".pdf": parse_docling,
    ".docx": parse_docling,
    ".pptx": parse_docling,
    ".xlsx": parse_docling,
    ".xls": parse_docling,
    ".csv": parse_csv,
    ".html": parse_html,
    ".htm": parse_html,
    ".json": parse_json,
    ".yaml": parse_text,
    ".yml": parse_text,
    ".log": parse_text,
    ".md": parse_text,
    ".txt": parse_text,
}

# Supported file extensions for upload (text + image)
SUPPORTED_EXTENSIONS = set(PARSERS.keys()) | IMAGE_EXTENSIONS

# Segment parsers for formats that have natural sub-document boundaries
SEGMENT_PARSERS = {
    ".pdf": lambda b, fn: parse_docling_segments(b, fn),
    ".docx": lambda b, fn: parse_docling_segments(b, fn),
    ".pptx": lambda b, fn: parse_docling_segments(b, fn),
    ".xlsx": lambda b, fn: parse_docling_segments(b, fn),
    ".xls": lambda b, fn: parse_docling_segments(b, fn),
}


def parse_file_segments(file_bytes: bytes, filename: str) -> list[ParsedSegment]:
    """Parse a file into segments with metadata.

    For PDF/DOCX/PPTX/Excel, returns per-page/slide/sheet segments.
    For other text formats, returns a single segment with empty metadata.

    Raises:
        ValueError: If the file format is not supported.
    """
    ext = Path(filename).suffix.lower()
    seg_parser = SEGMENT_PARSERS.get(ext)
    if seg_parser:
        return seg_parser(file_bytes, filename)

    parser = PARSERS.get(ext)
    if not parser:
        raise ValueError(
            f"Unsupported file format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    content = parser(file_bytes, filename)
    if not content.strip():
        return []
    return [ParsedSegment(content=content)]


def parse_file(file_bytes: bytes, filename: str) -> str:
    """Parse a file and extract text content.

    Args:
        file_bytes: Raw file bytes.
        filename: Original filename (used to determine format).

    Returns:
        Extracted text content.

    Raises:
        ValueError: If the file format is not supported.
    """
    segments = parse_file_segments(file_bytes, filename)
    return "\n\n".join(seg.content for seg in segments)
