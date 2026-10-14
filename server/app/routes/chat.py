"""What the browser needs to answer a question with its own Ollama.

The browser calls these in order: /api/expand, then embeds the expanded
question with Ollama, then /api/retrieve with that embedding, then streams the
answer from Ollama. Config comes from /api/config once at startup.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import abbreviations, config, db, embedding, retrieval, settings

router = APIRouter(prefix="/api")


def _index_meta(conn) -> dict | None:
    row = conn.execute(
        "SELECT embed_model, embed_dimensions, parent_chunk_size, child_chunk_size,"
        " parent_chunk_overlap, updated_at FROM index_meta"
    ).fetchone()
    return dict(row) if row else None


@router.get("/config")
def get_config():
    with db.connection() as conn:
        meta = _index_meta(conn)
        s = settings.current(conn)
    return {
        "llm_model": config.LLM_MODEL_NAME,
        # Edited in the app's settings; every conversation uses the current ones.
        "system_prompt": s["system_prompt"],
        "no_answer_response": s["no_answer_response"],
        "answer_without_sources": s["answer_without_sources"],
        "history_max_turns": s["history_max_turns"],
        "query_max_length": s["query_max_length"],
        "llm_options": {
            "temperature": s["llm_temperature"],
            "top_p": s["llm_top_p"],
            "top_k": s["llm_top_k"],
            "num_ctx": s["llm_num_ctx"],
            "num_predict": s["llm_max_tokens"],
        },
        # The embedding model is not a choice: a question has to be embedded
        # with the model the index was built with, or the vectors mean nothing.
        "embed_model": meta["embed_model"] if meta else None,
        # Put before the question when embedding it (see app/embedding.py).
        "query_prefix": embedding.query_prefix(meta["embed_model"] if meta else None),
    }


class ExpandRequest(BaseModel):
    query: str
    # Only abbreviations from the conversation's index are used.
    index_id: int


@router.post("/expand")
def expand(request: ExpandRequest):
    with db.connection() as conn:
        max_length = settings.current(conn)["query_max_length"]
        if len(request.query) > max_length:
            raise HTTPException(status_code=422, detail=f"De vraag is langer dan {max_length} tekens.")
        tokens = [t.upper() for t in abbreviations.query_tokens(request.query)]
        if not tokens:
            return {"query": request.query, "expansions": []}
        rows = conn.execute(
            "SELECT abbrev, term, source_url, file_name, snippet FROM abbreviations"
            " WHERE upper(abbrev) = ANY(%s)"
            " AND document_id IN (SELECT document_id FROM index_documents WHERE index_id = %s)"
            " ORDER BY id",
            (tokens, request.index_id),
        ).fetchall()
    by_abbrev: dict[str, list[dict]] = {}
    for row in rows:
        by_abbrev.setdefault(row["abbrev"].upper(), []).append(dict(row))
    query, expansions = abbreviations.expand_query(request.query, by_abbrev)
    return {"query": query, "expansions": expansions}


class RetrieveRequest(BaseModel):
    embedding: list[float] = Field(min_length=1)
    embed_model: str
    index_id: int
    # The (expanded) question as text, for the keyword half of hybrid search.
    query: str = Field(default="", max_length=100_000)


@router.post("/retrieve")
def retrieve(request: RetrieveRequest):
    with db.connection() as conn:
        meta = _index_meta(conn)
        s = settings.current(conn)
    if meta is None:
        raise HTTPException(
            status_code=409,
            detail="Er is nog niets geïndexeerd. Open Index in de zijbalk om te indexeren.",
        )
    if request.embed_model != meta["embed_model"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"De index is gebouwd met {meta['embed_model']}, "
                f"de vraag is ingebed met {request.embed_model}."
            ),
        )
    try:
        contexts = retrieval.retrieve(
            request.embedding,
            request.index_id,
            top_k=s["retrieval_top_k"],
            top_n=s["context_top_n"],
            threshold=s["automerge_threshold"],
            min_similarity=s["min_similarity"],
            query=request.query,
            hybrid=s["hybrid_search"],
            relative_similarity=s["relative_similarity"],
        )
    except retrieval.DimensionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"contexts": contexts}
