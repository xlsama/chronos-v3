"""File parsers for extracting text from various document formats."""

import csv
import io
from pathlib import Path


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


def parse_pdf(file_bytes: bytes, _filename: str = "") -> str:
    """Parse PDF files using pymupdf."""
    import pymupdf

    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n\n".join(pages)


def parse_docx(file_bytes: bytes, _filename: str = "") -> str:
    """Parse Word (.docx) files using python-docx."""
    import docx

    doc = docx.Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def parse_excel(file_bytes: bytes, filename: str = "") -> str:
    """Parse Excel (.xlsx/.xls) files using openpyxl."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheets = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        lines = [f"### Sheet: {sheet_name}"]
        header = [str(c) if c is not None else "" for c in rows[0]]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in rows[1:]:
            cells = [str(c) if c is not None else "" for c in row]
            padded = cells + [""] * (len(header) - len(cells))
            lines.append("| " + " | ".join(padded[:len(header)]) + " |")
        sheets.append("\n".join(lines))
    wb.close()
    return "\n\n".join(sheets)


# Mapping of file extensions to parser functions
PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".xlsx": parse_excel,
    ".xls": parse_excel,
    ".csv": parse_csv,
    ".md": parse_text,
    ".txt": parse_text,
}

# Supported file extensions for upload
SUPPORTED_EXTENSIONS = set(PARSERS.keys())


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
    ext = Path(filename).suffix.lower()
    parser = PARSERS.get(ext)
    if not parser:
        raise ValueError(
            f"Unsupported file format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return parser(file_bytes, filename)
