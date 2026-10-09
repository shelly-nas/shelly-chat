"""The document index, filled by the indexer on the Ollama machine.

The indexer (host/indexing) fetches documents from GitLab, chunks them and
embeds the chunks with its local Ollama, then stores them here. Everything but
GET /api/index needs the INDEX_TOKEN as a bearer token.

Each document is replaced as a whole in one transaction, so a search never
sees half a document and an interrupted run simply resumes on the next one.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import abbreviations, config, db

router = APIRouter(prefix="/api/index")


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not config.INDEX_TOKEN:
        return
    expected = f"Bearer {config.INDEX_TOKEN}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Ongeldige of ontbrekende INDEX_TOKEN.")


_META_COLUMNS = (
    "embed_model, embed_dimensions, parent_chunk_size, child_chunk_size,"
    " parent_chunk_overlap, updated_at"
)


@router.get("")
def index_status():
    """Public summary for the settings screen."""
    with db.connection() as conn:
        meta = conn.execute(f"SELECT {_META_COLUMNS} FROM index_meta").fetchone()
        counts = conn.execute(
            "SELECT"
            " (SELECT count(*) FROM documents) AS documents,"
            " (SELECT count(*) FROM chunks) AS chunks,"
            " (SELECT count(*) FROM abbreviations) AS abbreviations,"
            " (SELECT max(indexed_at) FROM documents) AS last_indexed_at"
        ).fetchone()
    return {"meta": meta, **counts}


class IndexMeta(BaseModel):
    embed_model: str = Field(min_length=1)
    embed_dimensions: int = Field(gt=0)
    parent_chunk_size: int = Field(gt=0)
    child_chunk_size: int = Field(gt=0)
    parent_chunk_overlap: int = Field(ge=0)
    # Drop every document first. Required when any of the fields above
    # changes: vectors from two models, or chunks of two sizes, do not mix.
    reset: bool = False


@router.put("/meta", dependencies=[Depends(require_token)])
def put_meta(request: IndexMeta):
    fields = request.model_dump(exclude={"reset"})
    with db.connection() as conn:
        current = conn.execute(f"SELECT {_META_COLUMNS} FROM index_meta").fetchone()
        changed = current is not None and any(current[k] != v for k, v in fields.items())
        if changed and not request.reset:
            raise HTTPException(
                status_code=409,
                detail="De indexconfiguratie verschilt; stuur reset=true om opnieuw te beginnen.",
            )
        if request.reset:
            conn.execute("TRUNCATE documents, chunks, abbreviations")
        meta = conn.execute(
            "INSERT INTO index_meta (embed_model, embed_dimensions, parent_chunk_size,"
            " child_chunk_size, parent_chunk_overlap)"
            " VALUES (%(embed_model)s, %(embed_dimensions)s, %(parent_chunk_size)s,"
            " %(child_chunk_size)s, %(parent_chunk_overlap)s)"
            " ON CONFLICT (id) DO UPDATE SET embed_model = EXCLUDED.embed_model,"
            " embed_dimensions = EXCLUDED.embed_dimensions,"
            " parent_chunk_size = EXCLUDED.parent_chunk_size,"
            " child_chunk_size = EXCLUDED.child_chunk_size,"
            " parent_chunk_overlap = EXCLUDED.parent_chunk_overlap,"
            " updated_at = now()"
            f" RETURNING {_META_COLUMNS}",
            fields,
        ).fetchone()
    return {"meta": meta, "reset": request.reset}


@router.get("/documents", dependencies=[Depends(require_token)])
def list_documents():
    """file_path and content_hash of everything indexed, for change detection."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT file_path, content_hash, indexed_at FROM documents ORDER BY file_path"
        ).fetchall()
    return {"documents": rows}


class Node(BaseModel):
    id: str = Field(min_length=1)
    parent_id: str | None = None
    is_leaf: bool
    position: int
    content: str
    metadata: dict = Field(default_factory=dict)
    embedding: list[float] | None = None


class Document(BaseModel):
    file_path: str = Field(min_length=1)
    file_name: str = ""
    source_url: str = ""
    content_hash: str = Field(min_length=1)
    content: str = ""
    metadata: dict = Field(default_factory=dict)
    nodes: list[Node] = Field(min_length=1)


def _store_abbreviations(conn, document_id: int, text: str, source_url: str, file_name: str) -> int:
    conn.execute("DELETE FROM abbreviations WHERE document_id = %s", (document_id,))
    entries = abbreviations.extract_abbreviations(text, source_url, file_name)
    if entries:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO abbreviations (document_id, abbrev, term, source_url, file_name, snippet)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (document_id, e["abbrev"], e["term"], e["source_url"], e["file_name"], e["snippet"])
                    for e in entries
                ],
            )
    return len(entries)


@router.put("/documents", dependencies=[Depends(require_token)])
def put_document(document: Document):
    with db.connection() as conn:
        meta = conn.execute("SELECT embed_dimensions FROM index_meta").fetchone()
        if meta is None:
            raise HTTPException(
                status_code=409, detail="Zet eerst de indexconfiguratie via PUT /api/index/meta."
            )
        for node in document.nodes:
            if node.is_leaf and node.embedding is None:
                raise HTTPException(status_code=422, detail=f"Leaf {node.id} heeft geen embedding.")
            if node.embedding is not None and len(node.embedding) != meta["embed_dimensions"]:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Chunk {node.id} heeft {len(node.embedding)} dimensies,"
                        f" de index {meta['embed_dimensions']}."
                    ),
                )

        conn.execute("DELETE FROM documents WHERE file_path = %s", (document.file_path,))
        document_id = conn.execute(
            "INSERT INTO documents (file_path, file_name, source_url, content_hash, content, metadata)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (
                document.file_path,
                document.file_name,
                document.source_url,
                document.content_hash,
                document.content,
                Jsonb(document.metadata),
            ),
        ).fetchone()["id"]

        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (id, document_id, parent_id, is_leaf, position, content, metadata, embedding)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)",
                [
                    (
                        n.id,
                        document_id,
                        n.parent_id,
                        n.is_leaf,
                        n.position,
                        n.content,
                        Jsonb(n.metadata),
                        db.vector_literal(n.embedding) if n.embedding is not None else None,
                    )
                    for n in document.nodes
                ],
            )

        abbreviation_count = _store_abbreviations(
            conn, document_id, document.content, document.source_url, document.file_name
        )
    return {
        "file_path": document.file_path,
        "chunks": len(document.nodes),
        "abbreviations": abbreviation_count,
    }


@router.delete("/documents", status_code=204, dependencies=[Depends(require_token)])
def delete_document(file_path: str):
    with db.connection() as conn:
        conn.execute("DELETE FROM documents WHERE file_path = %s", (file_path,))
    return Response(status_code=204)


@router.post("/abbreviations", dependencies=[Depends(require_token)])
def rebuild_abbreviations():
    """Extract the abbreviations of every stored document again, without re-embedding."""
    total = 0
    with db.connection() as conn:
        documents = conn.execute(
            "SELECT id, content, source_url, file_name FROM documents"
        ).fetchall()
        for d in documents:
            total += _store_abbreviations(conn, d["id"], d["content"], d["source_url"], d["file_name"])
    return {"documents": len(documents), "abbreviations": total}
