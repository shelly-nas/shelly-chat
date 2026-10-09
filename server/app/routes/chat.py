"""What the browser needs to answer a question with its own Ollama.

The browser calls these in order: /api/expand, then embeds the expanded
question with Ollama, then /api/retrieve with that embedding, then streams the
answer from Ollama. Config comes from /api/config once at startup.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app import abbreviations, config, db, retrieval

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
    return {
        "llm_model": config.LLM_MODEL_NAME,
        "system_prompt": config.LLM_SYSTEM_PROMPT,
        "no_answer_response": config.NO_ANSWER_RESPONSE,
        "history_max_turns": config.CHAT_HISTORY_MAX_TURNS,
        "query_max_length": config.QUERY_MAX_LENGTH,
        "llm_options": {
            "temperature": config.LLM_TEMPERATURE,
            "top_p": config.LLM_TOP_P,
            "top_k": config.LLM_TOP_K,
            "num_ctx": config.LLM_NUM_CTX,
        },
        # The embedding model is not a choice: a question has to be embedded
        # with the model the index was built with, or the vectors mean nothing.
        "embed_model": meta["embed_model"] if meta else None,
    }


class ExpandRequest(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def query_length(cls, v: str) -> str:
        if len(v) > config.QUERY_MAX_LENGTH:
            raise ValueError(
                f"De vraag is langer dan {config.QUERY_MAX_LENGTH} tekens."
            )
        return v


@router.post("/expand")
def expand(request: ExpandRequest):
    tokens = [t.upper() for t in abbreviations.query_tokens(request.query)]
    if not tokens:
        return {"query": request.query, "expansions": []}
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT abbrev, term, source_url, file_name, snippet FROM abbreviations"
            " WHERE upper(abbrev) = ANY(%s) ORDER BY id",
            (tokens,),
        ).fetchall()
    by_abbrev: dict[str, list[dict]] = {}
    for row in rows:
        by_abbrev.setdefault(row["abbrev"].upper(), []).append(dict(row))
    query, expansions = abbreviations.expand_query(request.query, by_abbrev)
    return {"query": query, "expansions": expansions}


class RetrieveRequest(BaseModel):
    embedding: list[float] = Field(min_length=1)
    embed_model: str


@router.post("/retrieve")
def retrieve(request: RetrieveRequest):
    with db.connection() as conn:
        meta = _index_meta(conn)
    if meta is None:
        raise HTTPException(
            status_code=409,
            detail="Er is nog niets geïndexeerd. Draai eerst de indexer (zie host/README.md).",
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
        contexts = retrieval.default_retrieve(request.embedding)
    except retrieval.DimensionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"contexts": contexts}
