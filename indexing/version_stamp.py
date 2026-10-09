"""Version stamp: detect embed-model/chunk-config drift via Qdrant.

A dedicated `index_meta` collection holds exactly one point whose payload
records the embed model and chunk sizes the index was built with. When the
current .env config no longer matches the stored stamp, the indexer triggers
an automatic full reindex instead of relying on a human remembering to pass
--full-reindex. The stamp is written immediately after a full-reindex reset so
an interrupted rebuild resumes incrementally instead of wiping again.
"""

from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

INDEX_META_COLLECTION = "index_meta"
_STAMP_POINT_ID = 1


def read_stamp(qdrant_client: QdrantClient) -> Optional[dict]:
    """Return the stored config stamp, or None if no stamp exists yet."""
    collections = {c.name for c in qdrant_client.get_collections().collections}
    if INDEX_META_COLLECTION not in collections:
        return None
    points = qdrant_client.retrieve(
        collection_name=INDEX_META_COLLECTION,
        ids=[_STAMP_POINT_ID],
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        return None
    return dict(points[0].payload or {})


def write_stamp(qdrant_client: QdrantClient, stamp: dict) -> None:
    """Upsert the single stamp point, creating the collection if needed.

    The collection needs a vector config even though it is never searched;
    a 1-dimensional dummy vector keeps it independent of the real embed
    model's dimensionality.
    """
    collections = {c.name for c in qdrant_client.get_collections().collections}
    if INDEX_META_COLLECTION not in collections:
        qdrant_client.create_collection(
            collection_name=INDEX_META_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
    qdrant_client.upsert(
        collection_name=INDEX_META_COLLECTION,
        points=[PointStruct(id=_STAMP_POINT_ID, vector=[0.0], payload=stamp)],
    )


def delete_stamp(qdrant_client: QdrantClient) -> None:
    """Drop the index_meta collection (part of a full-reindex clean slate)."""
    collections = {c.name for c in qdrant_client.get_collections().collections}
    if INDEX_META_COLLECTION in collections:
        qdrant_client.delete_collection(INDEX_META_COLLECTION)
