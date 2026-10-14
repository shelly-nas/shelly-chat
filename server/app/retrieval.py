"""Finding the sources for a question, on a query embedding made by the browser.

1. Search, in the leaf chunks of the conversation's index:
   - by meaning: exact cosine search on the embeddings (top-K), and
   - by keywords (hybrid search): Postgres full-text search with Dutch and
     English word forms, for what vectors miss - names, numbers, exact terms.
   The two lists are merged with reciprocal rank fusion: a chunk high in both
   ranks first. Without keywords (or with hybrid search off) the order is
   simply the cosine order.
2. Relevance: a chunk counts only when its cosine similarity reaches the
   absolute floor (min_similarity) and lies within relative_similarity of
   the best chunk. With nothing left, the model is not given sources.
3. Auto-merge: when more than AUTOMERGE_THRESHOLD of a parent's leaves were
   found, the parent (the whole section) replaces them. It ranks as its best
   leaf plus a bonus for each other one, so finding more of a section lifts
   it instead of averaging it down.
4. Diversity: the top-N are chosen with maximal marginal relevance, so the
   model gets relevant sources that do not repeat each other (overlapping
   sections otherwise often come back twice).

No model runs here: cross-encoder reranking would put one on the NAS.
"""

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field

from app import config, db

# Reciprocal rank fusion: score = sum of 1 / (RRF_K + rank) over the lists.
# 60 is the usual constant; it keeps one list from dominating.
RRF_K = 60
# A merged section ranks as its best leaf plus this share of the others.
MERGE_BONUS = 0.5


@dataclass
class Hit:
    id: str
    parent_id: str | None
    content: str
    metadata: dict
    file_path: str
    file_name: str
    source_url: str
    # Cosine similarity with the question: shown as "Relevantie" and used for the thresholds.
    score: float
    chunk_type: str = "child"
    merged_ids: list[str] = field(default_factory=list)
    # The order: reciprocal rank fusion of the vector and keyword lists.
    rank: float = 0.0
    embedding: list[float] | None = None


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
            ranks = sorted((c.rank for c in children), reverse=True)
            embeddings = [c.embedding for c in children if c.embedding]
            merged.append(
                Hit(
                    id=parent.id,
                    parent_id=parent.parent_id,
                    content=parent.content,
                    metadata=parent.metadata,
                    file_path=parent.file_path,
                    file_name=parent.file_name,
                    source_url=parent.source_url,
                    score=max(c.score for c in children),
                    chunk_type="parent",
                    merged_ids=[c.id for c in children],
                    rank=ranks[0] + MERGE_BONUS * sum(ranks[1:]),
                    embedding=_mean(embeddings) if embeddings else None,
                )
            )
            merged_away.update(c.id for c in children)

    result = [h for h in hits if h.id not in merged_away] + merged
    return sorted(result, key=lambda h: h.rank, reverse=True)


def relevant(hits: list[Hit], min_similarity: float, relative_similarity: float) -> list[Hit]:
    """Hits at or above the floor, and within relative_similarity of the best (0: no relative limit)."""
    hits = [h for h in hits if h.score >= min_similarity]
    if hits and relative_similarity > 0:
        best = max(h.score for h in hits)
        hits = [h for h in hits if h.score >= best - relative_similarity]
    return hits


def fuse(*lists: list[Hit]) -> list[Hit]:
    """Reciprocal rank fusion of ranked lists of the same leaves; best first."""
    fused: dict[str, Hit] = {}
    for hits in lists:
        for rank, hit in enumerate(hits, start=1):
            fused.setdefault(hit.id, hit).rank += 1 / (RRF_K + rank)
    return sorted(fused.values(), key=lambda h: h.rank, reverse=True)


def diverse(hits: list[Hit], top_n: int, mmr_lambda: float) -> list[Hit]:
    """Maximal marginal relevance: each next source is relevant and unlike the ones chosen."""
    if mmr_lambda >= 1 or len(hits) <= 1:
        return hits[:top_n]
    best_rank = max(h.rank for h in hits) or 1
    chosen: list[Hit] = []
    left = list(hits)
    while left and len(chosen) < top_n:
        def value(h: Hit) -> float:
            overlap = max((_cosine(h.embedding, c.embedding) for c in chosen), default=0.0)
            return mmr_lambda * h.rank / best_rank - (1 - mmr_lambda) * overlap

        pick = max(left, key=value)
        chosen.append(pick)
        left.remove(pick)
    return chosen


def _mean(vectors: list[list[float]]) -> list[float]:
    return [sum(xs) / len(vectors) for xs in zip(*vectors)]


def _cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


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

_LEAVES_IN_INDEX = """
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.is_leaf AND c.embedding IS NOT NULL
      AND c.document_id IN (SELECT document_id FROM index_documents WHERE index_id = %(i)s)
"""

# Any of the question's words counts (OR), in Dutch and in English word forms;
# plainto_tsquery drops stop words and joins the rest with AND, hence the replace.
_KEYWORDS = """
    (replace(plainto_tsquery('dutch', %(q)s)::text, '&', '|')::tsquery
     || replace(plainto_tsquery('english', %(q)s)::text, '&', '|')::tsquery)
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
        embedding=json.loads(row["vec"]) if row.get("vec") else None,
    )


def retrieve(
    embedding: list[float],
    index_id: int,
    top_k: int,
    top_n: int,
    threshold: float,
    min_similarity: float = 0.0,
    *,
    query: str = "",
    hybrid: bool = True,
    relative_similarity: float = 0.0,
    mmr_lambda: float | None = None,
) -> list[dict]:
    """The top_n contexts for a question; see the module docstring for the steps.

    With nothing relevant, the result is empty: the answer comes without sources.
    """
    mmr_lambda = config.MMR_LAMBDA if mmr_lambda is None else mmr_lambda
    vector = db.vector_literal(embedding)
    params = {"v": vector, "k": top_k, "i": index_id, "q": query}
    with db.connection() as conn:
        meta = conn.execute("SELECT embed_dimensions FROM index_meta").fetchone()
        if meta is None:
            return []
        if meta["embed_dimensions"] != len(embedding):
            raise DimensionMismatch(
                f"De index gebruikt {meta['embed_dimensions']} dimensies, "
                f"de vraag heeft er {len(embedding)}."
            )

        # 1. By meaning, and by keywords.
        by_vector = [
            _hit(r, float(r["score"]))
            for r in conn.execute(
                f"SELECT {_HIT_COLUMNS}, c.embedding::text AS vec,"
                f" 1 - (c.embedding <=> %(v)s::vector) AS score {_LEAVES_IN_INDEX}"
                " ORDER BY c.embedding <=> %(v)s::vector LIMIT %(k)s",
                params,
            )
        ]
        by_keyword: list[Hit] = []
        if hybrid and query.strip():
            by_keyword = [
                _hit(r, float(r["score"]))
                for r in conn.execute(
                    f"SELECT {_HIT_COLUMNS}, c.embedding::text AS vec,"
                    f" 1 - (c.embedding <=> %(v)s::vector) AS score {_LEAVES_IN_INDEX}"
                    f" AND c.tsv @@ {_KEYWORDS}"
                    f" ORDER BY ts_rank_cd(c.tsv, {_KEYWORDS}) DESC LIMIT %(k)s",
                    params,
                )
            ]
        # 2. Only what is relevant enough.
        hits = relevant(fuse(by_vector, by_keyword), min_similarity, relative_similarity)
        if not hits:
            return []

        parent_ids = list({h.parent_id for h in hits if h.parent_id})
        parents: dict[str, Hit] = {}
        child_counts: dict[str, int] = {}
        if parent_ids:
            for r in conn.execute(
                f"SELECT {_HIT_COLUMNS} FROM chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE c.id = ANY(%s)",
                (parent_ids,),
            ):
                parents[r["id"]] = _hit(r)
            for r in conn.execute(
                "SELECT parent_id, count(*) AS n FROM chunks"
                " WHERE parent_id = ANY(%s) GROUP BY parent_id",
                (parent_ids,),
            ):
                child_counts[r["parent_id"]] = r["n"]

    # 3-4. Whole sections where enough of them was found, then a varied top-N.
    ranked = diverse(auto_merge(hits, parents, child_counts, threshold), top_n, mmr_lambda)
    return [to_context(h, i + 1) for i, h in enumerate(ranked)]
