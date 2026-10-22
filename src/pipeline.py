"""File bytes -> text -> structured data. Never raises for bad input."""
import re
from pathlib import Path

import pymupdf  # PyMuPDF

from .extract_fields import extract_fields
from .ocr_reader import (OCRError, OCRUnavailableError, ocr_image_bytes,
                         ocr_pdf_bytes)
from .validation import validate_document

MAX_FILE_BYTES = 10 * 1024 * 1024        # 10 MB
MAX_PDF_PAGES = 10
MIN_USABLE_CHARS = 30                    # fewer letters/digits than this = scanned PDF
PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
OCR_HINT = "OCR is optional and not installed. Run: pip install -r requirements-ocr.txt"


def pdf_page_text(page) -> str:
    """Page text with table columns kept on one line.

    Words are grouped by vertical position; a wide horizontal gap becomes 3
    spaces so the extractor can see the column boundaries.
    """
    words = page.get_text("words")
    if not words:
        return ""
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, current, current_y = [], [], None
    for w in words:
        y = (w[1] + w[3]) / 2
        height = max(w[3] - w[1], 1.0)
        if current and abs(y - current_y) > height * 0.5:
            lines.append(current)
            current = []
        if not current:
            current_y = y
        current.append(w)
    if current:
        lines.append(current)
    out = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        text = line[0][4]
        for prev, cur in zip(line, line[1:]):
            height = max(cur[3] - cur[1], 1.0)
            text += ("   " if cur[0] - prev[2] > height * 1.2 else " ") + cur[4]
        out.append(text)
    return "\n".join(out)


def _usable(text: str) -> bool:
    return len(re.sub(r"\W+", "", text)) >= MIN_USABLE_CHARS


def read_pdf_text(file_bytes: bytes) -> str:
    """Embedded text of a digital PDF. Raises ValueError with a friendly message."""
    try:
        pdf = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception:
        raise ValueError("This PDF is corrupt or cannot be opened.")
    with pdf:
        if pdf.needs_pass or pdf.is_encrypted:
            raise ValueError("This PDF is password-protected. Remove the password and upload again.")
        if pdf.page_count == 0:
            raise ValueError("This PDF has no pages.")
        pages = [pdf_page_text(p) or p.get_text("text") for p in pdf if p.number < MAX_PDF_PAGES]
    return "\n".join(pages)


def _looks_like(file_bytes: bytes, suffix: str) -> bool:
    """Cheap check that the content matches the extension (magic bytes)."""
    if suffix in PDF_SUFFIXES:
        return file_bytes[:5] == b"%PDF-"
    if suffix == ".png":
        return file_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    return file_bytes[:3] == b"\xff\xd8\xff"          # JPEG


def process_document(file_bytes: bytes, filename: str, document_type: str) -> dict:
    """Return {filename, text_source, raw_text, data, warnings}. Errors become warnings."""
    from .extract_fields import empty_document
    suffix = Path(filename or "").suffix.lower()
    warnings: list[str] = []
    raw_text, text_source = "", "None"

    problem = None
    if not file_bytes:
        problem = "The file is empty."
    elif len(file_bytes) > MAX_FILE_BYTES:
        problem = f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB."
    elif suffix not in PDF_SUFFIXES | IMAGE_SUFFIXES:
        problem = "Unsupported file type. Use PDF, PNG, JPG or JPEG."
    elif not _looks_like(file_bytes, suffix):
        problem = "The file content does not match its extension, so it was not processed."

    if problem:
        warnings.append(problem)
    elif suffix in PDF_SUFFIXES:
        try:
            raw_text, text_source = read_pdf_text(file_bytes), "PyMuPDF (digital PDF)"
        except ValueError as exc:
            warnings.append(str(exc))
        if not warnings and not _usable(raw_text):
            warnings.append("The PDF has little or no embedded text; trying OCR.")
            raw_text, text_source = _try_ocr(lambda: ocr_pdf_bytes(file_bytes, MAX_PDF_PAGES),
                                             warnings, "PaddleOCR (scanned PDF)")
    else:
        raw_text, text_source = _try_ocr(lambda: ocr_image_bytes(file_bytes, suffix),
                                         warnings, "PaddleOCR (image)")

    if problem or not raw_text.strip():
        data, field_warnings = empty_document(document_type), []
        if not problem and not any("No text" in w for w in warnings):
            warnings.append("No usable text was found in this file.")
    else:
        data, field_warnings = extract_fields(raw_text, document_type)
    data["source_filename"] = filename
    data["document_type"] = document_type
    warnings.extend(field_warnings)
    if raw_text.strip():
        warnings.extend(validate_document(data))
    return {"filename": filename, "text_source": text_source, "raw_text": raw_text,
            "data": data, "warnings": warnings}


def _try_ocr(run, warnings: list[str], label: str) -> tuple[str, str]:
    try:
        return run(), label
    except OCRUnavailableError:
        warnings.append(OCR_HINT)
    except OCRError as exc:
        warnings.append(str(exc))
    except Exception as exc:                      # OCR must never crash the app
        warnings.append(f"OCR failed: {exc}")
    return "", "None"
