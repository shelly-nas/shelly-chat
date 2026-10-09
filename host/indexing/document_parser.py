"""Plain-text extraction from binary document formats.

Used by GitLab fetchers when downloading PDF or DOCX files via the API.
"""

import io


def parse_pdf_bytes(data: bytes, filename: str = "") -> str:
    """Extract text from a PDF given raw bytes."""
    try:
        from pdfminer.high_level import extract_text
    except ImportError:
        raise ImportError(
            "pdfminer.six is required for PDF parsing: pip install pdfminer.six"
        )
    try:
        return extract_text(io.BytesIO(data)) or ""
    except Exception as exc:
        raise ValueError(f"Failed to parse PDF '{filename}': {exc}") from exc


def parse_docx_bytes(data: bytes, filename: str = "") -> str:
    """Extract text from a DOCX (or .doc) file given raw bytes.

    python-docx handles .docx natively. For legacy .doc files it may succeed
    on newer-format .doc files; otherwise a ValueError is raised.
    """
    try:
        import docx
    except ImportError:
        raise ImportError(
            "python-docx is required for DOCX parsing: pip install python-docx"
        )
    try:
        document = docx.Document(io.BytesIO(data))
        return "\n".join(para.text for para in document.paragraphs)
    except Exception as exc:
        raise ValueError(f"Failed to parse DOCX '{filename}': {exc}") from exc
