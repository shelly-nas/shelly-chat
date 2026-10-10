"""A document as fetched from GitLab, before the NAS turns it into chunks."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Document:
    """Either `text` (Markdown) or `data_base64` (file bytes for the NAS to
    extract, e.g. PDF or DOCX). `metadata` carries file_path, file_name and
    source_url, plus source-specific keys."""

    metadata: dict = field(default_factory=dict)
    text: Optional[str] = None
    data_base64: Optional[str] = None
