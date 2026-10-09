"""Change detection via Qdrant point payloads: track indexed files without a manifest.

Every indexed child node carries `content_hash` (SHA-256 of the source document
text) and `file_path` in its Qdrant payload. On each run one scroll pass reads
these back and classifies freshly fetched documents as new, changed, deleted,
or unchanged — so unchanged documents skip re-embedding entirely. Qdrant is the
single source of truth; there is no sidecar manifest file to fall out of sync.
"""

import hashlib
from typing import Dict, List, Tuple

from llama_index.core import Document
from qdrant_client import QdrantClient


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_indexed_hashes(
    qdrant_client: QdrantClient,
    collection_name: str,
) -> Dict[str, str]:
    """Scroll the full collection once, return {file_path: content_hash}.

    Deduplicates across the many child points per file (all points for a given
    file_path carry the same document-level content_hash). Returns {} if the
    collection does not exist yet (fresh install).
    """
    collections = {c.name for c in qdrant_client.get_collections().collections}
    if collection_name not in collections:
        return {}

    hashes: Dict[str, str] = {}
    offset = None
    while True:
        points, offset = qdrant_client.scroll(
            collection_name=collection_name,
            with_payload=["file_path", "content_hash"],
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for point in points:
            payload = point.payload or {}
            fp = payload.get("file_path", "")
            ch = payload.get("content_hash", "")
            if fp and ch:
                hashes[fp] = ch
        if offset is None:
            break
    return hashes


def classify_documents(
    documents: List[Document],
    indexed_hashes: Dict[str, str],
) -> Tuple[List[Document], List[Document], List[str], List[Document]]:
    """Classify fetched documents against the hashes stored in Qdrant.

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
