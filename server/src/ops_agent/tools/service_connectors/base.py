from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ServiceResult:
    success: bool
    output: str           # Formatted plain text
    error: str | None = None
    row_count: int | None = None


class ServiceConnector(ABC):
    service_type: str = ""

    @abstractmethod
    async def execute(self, command: str) -> ServiceResult: ...

    @abstractmethod
    async def close(self) -> None: ...


def format_as_table(columns: list[str], rows: list[tuple]) -> str:
    """Format SQL result as Markdown table."""
    if not columns:
        return "(empty result)"

    # Convert all values to strings
    str_rows = [[str(v) for v in row] for row in rows]

    # Calculate column widths
    widths = [len(c) for c in columns]
    for row in str_rows:
        for i, val in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(val))

    # Build table
    header = "| " + " | ".join(c.ljust(w) for c, w in zip(columns, widths)) + " |"
    separator = "|-" + "-|-".join("-" * w for w in widths) + "-|"

    lines = [header, separator]
    for row in str_rows:
        line = "| " + " | ".join(
            (row[i] if i < len(row) else "").ljust(w) for i, w in enumerate(widths)
        ) + " |"
        lines.append(line)

    lines.append(f"\n({len(str_rows)} rows)")
    return "\n".join(lines)
