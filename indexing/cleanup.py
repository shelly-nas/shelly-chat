"""Cleanup helpers: remove stale Qdrant points and docstore nodes by file_path.

Called before re-indexing a changed document or removing a deleted one so that
no orphaned vectors or wees-nodes remain.
"""

from indexing.console import log_info
from llama_index.core.storage.docstore import SimpleDocumentStore
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue


def delete_qdrant_points_by_file_path(
    qdrant_client: QdrantClient,
    collection_name: str,
    file_path: str,
) -> int:
    """Delete all Qdrant points whose file_path payload matches file_path.

    Returns the number of deleted points.
    """
    # LlamaIndex's QdrantVectorStore stores node metadata as flat top-level
    # payload keys, so the filter key is "file_path" — not "metadata.file_path",
    # which matches nothing.
    filt = Filter(
        must=[
            FieldCondition(
                key="file_path",
                match=MatchValue(value=file_path),
            )
        ]
    )

    count_result = qdrant_client.count(
        collection_name=collection_name,
        count_filter=filt,
        exact=True,
    )
    count = count_result.count

    if count > 0:
        qdrant_client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(filter=filt),
        )
        log_info(f"  Qdrant: {count} punt(en) verwijderd voor {file_path}")

    return count


def delete_docstore_nodes_by_file_path(
    docstore: SimpleDocumentStore,
    file_path: str,
) -> int:
    """Delete all nodes from the docstore where metadata.file_path matches.

    Returns the number of deleted nodes.
    """
    to_delete = [
        node_id
        for node_id, node in docstore.docs.items()
        if node.metadata.get("file_path") == file_path
    ]

    for node_id in to_delete:
        docstore.delete_document(node_id)

    if to_delete:
        log_info(f"  Docstore: {len(to_delete)} node(s) verwijderd voor {file_path}")

    return len(to_delete)


def cleanup_file_path(
    qdrant_client: QdrantClient,
    collection_name: str,
    docstore: SimpleDocumentStore,
    file_path: str,
) -> None:
    """Remove all Qdrant points and docstore nodes for a given file_path."""
    delete_qdrant_points_by_file_path(qdrant_client, collection_name, file_path)
    delete_docstore_nodes_by_file_path(docstore, file_path)
