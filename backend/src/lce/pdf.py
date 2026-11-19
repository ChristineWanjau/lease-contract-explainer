"""PDF validation and text extraction, one string per page."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30


class UploadRejected(Exception):
    """A user-facing reason the upload can't be processed."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def extract_pages(data: bytes) -> list[str]:
    """Validate an uploaded PDF and return its text, one string per page."""
    if len(data) > MAX_BYTES:
        raise UploadRejected(413, "too_large", "This file is over the 10 MB limit.")
    if not data.startswith(b"%PDF-"):
        raise UploadRejected(415, "not_pdf", "This isn't a PDF. Please upload a PDF file.")
    try:
        reader = PdfReader(BytesIO(data))
        page_count = len(reader.pages)
        if page_count > MAX_PAGES:
            raise UploadRejected(
                413,
                "too_many_pages",
                f"This PDF has {page_count} pages; the limit is {MAX_PAGES} pages.",
            )
        pages = [page.extract_text() or "" for page in reader.pages]
    except UploadRejected:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError):
        raise UploadRejected(
            422, "unreadable_pdf", "This PDF couldn't be read. It may be damaged or encrypted."
        ) from None
    if not any(p.strip() for p in pages):
        raise UploadRejected(
            422,
            "scanned_pdf",
            "No text found. Scanned PDFs aren't supported yet; please upload a PDF with selectable text.",
        )
    return pages
