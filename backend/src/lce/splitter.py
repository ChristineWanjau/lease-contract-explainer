"""Clause-aware contract splitter.

A pure function: page texts in, chunks out. Each chunk carries its clause
identifier (or None) and the 1-based page it starts on. Chunk text is copied
verbatim from the pages so citations can always be traced back to the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A clause heading at the start of a line, e.g. "1. Rent", "2.3 Deposit",
# "Clause 4", "Section 5.1", "Article 7". The number is capped at 3 digits so
# lines starting with years or amounts ("2024 ...", "1500 ...") are not headings.
_HEADING = re.compile(
    r"""^\s*(?:
        (?:Clause|Section|Article)\s+(?P<word>\d{1,3}(?:\.\d{1,3})*)\b
      | (?P<num>\d{1,3}(?:\.\d{1,3})*)(?:\.|\))?\s+(?=[A-Z])
    )""",
    re.VERBOSE | re.IGNORECASE,
)

FALLBACK_CHUNK_SIZE = 1000
FALLBACK_OVERLAP = 150


@dataclass(frozen=True)
class Chunk:
    text: str
    clause: str | None
    page: int


def _heading_id(line: str) -> str | None:
    match = _HEADING.match(line)
    if not match:
        return None
    # The bare-number form must start with a capital letter after it; the
    # IGNORECASE flag also applies to the lookahead, so re-check it here.
    if match.group("num") is not None:
        rest = line[match.end():]
        if not rest[:1].isupper():
            return None
        return match.group("num")
    return match.group("word")


def split_clauses(pages: list[str]) -> list[Chunk]:
    """Split contract pages into clause chunks.

    Sub-items such as "(a)" stay inside their parent clause. Text before the
    first heading becomes a chunk with ``clause=None``. If the document has no
    recognisable headings, fall back to fixed-size overlapping chunks.
    """
    chunks: list[Chunk] = []
    current_lines: list[str] = []
    current_clause: str | None = None
    current_page = 1
    found_heading = False

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            chunks.append(Chunk(text=text, clause=current_clause, page=current_page))

    for page_no, page in enumerate(pages, start=1):
        for line in page.split("\n"):
            heading = _heading_id(line)
            if heading is not None:
                found_heading = True
                flush()
                current_lines = [line]
                current_clause = heading
                current_page = page_no
            else:
                if not current_lines or not "\n".join(current_lines).strip():
                    current_page = page_no
                current_lines.append(line)
    flush()

    if not found_heading:
        return _fixed_size_chunks(pages)
    return chunks


def _fixed_size_chunks(pages: list[str]) -> list[Chunk]:
    step = FALLBACK_CHUNK_SIZE - FALLBACK_OVERLAP
    chunks: list[Chunk] = []
    for page_no, page in enumerate(pages, start=1):
        text = page.strip()
        start = 0
        while start < len(text):
            piece = text[start : start + FALLBACK_CHUNK_SIZE].strip()
            if piece:
                chunks.append(Chunk(text=piece, clause=None, page=page_no))
            if start + FALLBACK_CHUNK_SIZE >= len(text):
                break
            start += step
    return chunks
