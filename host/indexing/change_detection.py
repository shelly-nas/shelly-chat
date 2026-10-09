"""Change detection against what the NAS has already indexed.

The NAS stores a SHA-256 `content_hash` per document (keyed by `file_path`).
Each run compares freshly fetched documents with those hashes, so unchanged
documents skip embedding entirely. The NAS database is the single source of
truth; there is no local manifest to fall out of sync.
"""

import hashlib
from typing import Dict, List, Tuple

from llama_index.core import Document


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_documents(
    documents: List[Document],
    indexed_hashes: Dict[str, str],
) -> Tuple[List[Document], List[Document], List[str], List[Document]]:
    """Classify fetched documents against the hashes stored on the NAS.

    Documents must already carry `content_hash` in their metadata (stamped by
    the pipeline before classification).

    Returns:
        (new_docs, changed_docs, deleted_paths, unchanged_docs)
    """
    current_paths: set = set()
    new_docs: List[Document] = []
    changed_docs: List[Document] = []
    unchanged_docs: List[Document] = []

    for doc in documents:
        fp = doc.metadata.get("file_path", "")
        current_paths.add(fp)
        content_hash = doc.metadata.get("content_hash") or compute_hash(doc.text)

        if fp not in indexed_hashes:
            new_docs.append(doc)
        elif indexed_hashes[fp] != content_hash:
            changed_docs.append(doc)
        else:
            unchanged_docs.append(doc)

    deleted_paths = [fp for fp in indexed_hashes if fp not in current_paths]
    return new_docs, changed_docs, deleted_paths, unchanged_docs
