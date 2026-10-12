"""Vector search with auto-merging, on a query embedding made by the browser.

1. Exact cosine search over the leaf chunks of the conversation's index (top-K).
2. Auto-merge: when more than AUTOMERGE_THRESHOLD of a parent's leaves were
   retrieved, the parent replaces them, scored as their average. This is the
   merge step of LlamaIndex's AutoMergingRetriever, which the previous
   version used.
3. Best first, top-N to the model.

There is no cross-encoder reranking step any more: that would put a model on
the NAS. The cosine scores from step 1 decide the order.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from app import db


@dataclass
class Hit:
    id: str
    parent_id: str | None
    content: str
    metadata: dict
    file_path: str
    file_name: str
    source_url: str
    score: float
    chunk_type: str = "child"
    merged_ids: list[str] = field(default_factory=list)


class DimensionMismatch(ValueError):
    pass


def auto_merge(
    hits: list[Hit],
    parents: dict[str, Hit],
    child_counts: dict[str, int],
    threshold: float,
) -> list[Hit]:
    """Replace groups of retrieved leaves by their parent; return best first.

    parents holds the parent chunk of every hit that has one, child_counts the
    total number of leaves under each parent.
    """
    by_parent: dict[str, list[Hit]] = defaultdict(list)
    for hit in hits:
        if hit.parent_id and hit.parent_id in parents:
            by_parent[hit.parent_id].append(hit)

    merged_away: set[str] = set()
    merged: list[Hit] = []
    for parent_id, children in by_parent.items():
        total = child_counts.get(parent_id) or 1
        if len(children) / total > threshold:
            parent = parents[parent_id]
            merged.append(
                Hit(
                    id=parent.id,
                    parent_id=parent.parent_id,
                    content=parent.content,
                    metadata=parent.metadata,
                    file_path=parent.file_path,
                    file_name=parent.file_name,
                    source_url=parent.source_url,
                    score=sum(c.score for c in children) / len(children),
                    chunk_type="parent",
                    merged_ids=[c.id for c in children],
                )
            )
            merged_away.update(c.id for c in children)

    result = [h for h in hits if h.id not in merged_away] + merged
    return sorted(result, key=lambda h: h.score, reverse=True)


def to_context(hit: Hit, source_num: int) -> dict:
    """The source shape the browser renders and puts into the prompt."""
    meta = hit.metadata or {}
    return {
        "content": hit.content,
        "file_path": hit.file_path or meta.get("file_name", ""),
        "source_url": hit.source_url,
        "page_number": meta.get("page_number", meta.get("page_label", 1)),
        "start_line": meta.get("start_line", 1),
        "end_line": meta.get("end_line", 1),
        "section_context": meta.get("section_context", ""),
        "similarity": round(float(hit.score), 4),
        "source_num": source_num,
        "chunk_type": hit.chunk_type,
    }


_HIT_COLUMNS = """
    c.id, c.parent_id, c.content, c.metadata,
    d.file_path, d.file_name, d.source_url
"""


def _hit(row: dict, score: float = 0.0) -> Hit:
    return Hit(
        id=row["id"],
        parent_id=row["parent_id"],
        content=row["content"],
        metadata=row["metadata"] or {},
        file_path=row["file_path"],
        file_name=row["file_name"],
        source_url=row["source_url"],
        score=score,
    )


def retrieve(embedding: list[float], index_id: int, top_k: int, top_n: int, threshold: float) -> list[dict]:
    vector = db.vector_literal(embedding)
    with db.connection() as conn:
        meta = conn.execute("SELECT embed_dimensions FROM index_meta").fetchone()
        if meta is None:
            return []
        if meta["embed_dimensions"] != len(embedding):
            raise DimensionMismatch(
                f"De index gebruikt {meta['embed_dimensions']} dimensies, "
                f"de vraag heeft er {len(embedding)}."
            )

        rows = conn.execute(
            f"""
            SELECT {_HIT_COLUMNS}, 1 - (c.embedding <=> %(v)s::vector) AS score
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.is_leaf AND c.embedding IS NOT NULL
              AND c.document_id IN (SELECT document_id FROM index_documents WHERE index_id = %(i)s)
            ORDER BY c.embedding <=> %(v)s::vector
            LIMIT %(k)s
            """,
            {"v": vector, "k": top_k, "i": index_id},
        ).fetchall()
        hits = [_hit(r, float(r["score"])) for r in rows]

        parent_ids = list({h.parent_id for h in hits if h.parent_id})
        parents: dict[str, Hit] = {}
        child_counts: dict[str, int] = {}
        if parent_ids:
            for r in conn.execute(
                f"""
                SELECT {_HIT_COLUMNS}
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.id = ANY(%s)
                """,
                (parent_ids,),
            ):
                parents[r["id"]] = _hit(r)
            for r in conn.execute(
                "SELECT parent_id, count(*) AS n FROM chunks"
                " WHERE parent_id = ANY(%s) GROUP BY parent_id",
                (parent_ids,),
            ):
                child_counts[r["parent_id"]] = r["n"]

    ranked = auto_merge(hits, parents, child_counts, threshold)[:top_n]
    return [to_context(h, i + 1) for i, h in enumerate(ranked)]

