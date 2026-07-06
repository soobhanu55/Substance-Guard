from __future__ import annotations

from io import BytesIO

import pdfplumber


def extract_text(pdf_bytes: bytes) -> str:
    """Extracts text from a (text-based, not scanned) PDF. The synthetic SDS/test-report
    set in this project is generated as text PDFs, so no OCR step is needed here."""
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:  # pdfplumber/pdfminer raise their own exception types on malformed input
        raise ValueError(f"Could not parse PDF: {exc}") from exc
    text = "\n\n".join(pages).strip()
    if not text:
        raise ValueError("No extractable text found in PDF (is it a scanned image?)")
    return text
