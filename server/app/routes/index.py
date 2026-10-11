"""The shared document store behind all indexes, and its global settings.

Documents come from the documents folder on the NAS. Indexing is driven from
where Ollama runs - the Index screen in the browser, or the CLI in host/ - one
named index at a time: list the index's files (GET /api/indexes/{id}/files),
have each one read, hashed and split here (POST /api/index/prepare), embed the
leaf chunks with Ollama, store them (PUT /api/index/documents), and finally
drop what left the index (POST /api/indexes/{id}/prune).

A document lives here once, however many indexes it is in; index_documents
says which. The embedding model and chunk configuration (index_meta) are
shared by all indexes. Everything but the GET summaries needs the INDEX_TOKEN
as a bearer token.

Each document is replaced as a whole in one transaction, so a search never
sees half a document and an interrupted run simply resumes on the next one.
"""

import hmac
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import abbreviations, config, db, documents, files

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
            " (SELECT count(*) FROM indexes) AS indexes,"
            " (SELECT max(indexed_at) FROM documents) AS last_indexed_at"
        ).fetchone()
    return {"meta": meta, **counts}


@router.get("/settings")
def index_settings():
    """What an indexing run needs to know up front: model, chunking, the folder."""
    with db.connection() as conn:
        meta = conn.execute(f"SELECT {_META_COLUMNS} FROM index_meta").fetchone()
    return {
        "meta": meta,
        "chunk_config": documents.chunk_config(),
        "documents_dir": config.DOCUMENTS_DIR,
        "documents_root_exists": files.root().is_dir(),
    }


@router.get("/browse")
def browse(path: str = ""):
    """Folders and documents directly inside a folder, to pick sources from."""
    try:
        return files.browse(path)
    except files.PathError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/auth", dependencies=[Depends(require_token)])
def check_token():
    """Lets the Index screen tell whether the token it has is the right one."""
    return {"ok": True}


class IndexMeta(BaseModel):
    embed_model: str = Field(min_length=1)
    embed_dimensions: int = Field(gt=0)
    # Drop every document first. Required when the model, its dimensions or
    # the chunk configuration change: vectors from two models, or chunks of
    # two sizes, do not mix.
    reset: bool = False


@router.put("/meta", dependencies=[Depends(require_token)])
def put_meta(request: IndexMeta):
    fields = {**request.model_dump(exclude={"reset"}), **documents.chunk_config()}
    with db.connection() as conn:
        current = conn.execute(f"SELECT {_META_COLUMNS} FROM index_meta").fetchone()
        changed = current is not None and any(current[k] != v for k, v in fields.items())
        if changed and not request.reset:
            raise HTTPException(
                status_code=409,
                detail="De indexconfiguratie verschilt; stuur reset=true om opnieuw te beginnen.",
            )
        if request.reset:
            # Every index loses its documents; the indexes and their sources stay.
            conn.execute("TRUNCATE documents, chunks, abbreviations, index_documents")
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


class PrepareRequest(BaseModel):
    file_path: str = Field(min_length=1)
    # The index being indexed: an unchanged document joins it right away.
    index_id: int | None = None


def add_to_index(conn, index_id: int | None, document_id: int) -> None:
    if index_id is not None:
        conn.execute(
            "INSERT INTO index_documents (index_id, document_id) VALUES (%s, %s)"
            " ON CONFLICT DO NOTHING",
            (index_id, document_id),
        )


@router.post("/prepare", dependencies=[Depends(require_token)])
def prepare_document(request: PrepareRequest):
    """Read, hash and split one document. Unchanged ones are not split again."""
    try:
        path = files.resolve(request.file_path)
    except files.PathError as exc:
        raise HTTPException(status_code=422, detail=f"{request.file_path}: {exc}")
    if not files.is_supported(path):
        raise HTTPException(status_code=404, detail=f"{request.file_path}: geen ondersteund document.")
    file_path = files.relative(path)
    try:
        text = documents.extract_text(path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"{file_path}: {exc}")
    if not text.strip():
        return {"file_path": file_path, "status": "empty"}

    hash_ = documents.content_hash(text)
    with db.connection() as conn:
        stored = conn.execute(
            "SELECT id, content_hash FROM documents WHERE file_path = %s", (file_path,)
        ).fetchone()
        if stored and stored["content_hash"] == hash_:
            # Already split and embedded, perhaps for another index.
            add_to_index(conn, request.index_id, stored["id"])
            return {"file_path": file_path, "status": "unchanged", "content_hash": hash_}

    file_name = path.name
    # The app opens the original through GET /api/files/<path>.
    source_url = "/api/files/" + quote(file_path)
    metadata = {"file_path": file_path, "file_name": file_name, "source_url": source_url}
    try:
        nodes = documents.split(text, metadata, hash_)
    except ValueError as exc:
        # E.g. metadata longer than a chunk when CHILD_CHUNK_SIZE is very small.
        raise HTTPException(status_code=422, detail=f"{file_path}: {exc}")
    return {
        "file_path": file_path,
        "status": "changed" if stored else "new",
        "content_hash": hash_,
        "document": {
            "file_path": file_path,
            "file_name": file_name,
            "source_url": source_url,
            "content_hash": hash_,
            "content": text,
            "metadata": metadata,
            "nodes": nodes,
        },
    }


class Node(BaseModel):
    id: str = Field(min_length=1)
    parent_id: str | None = None
    is_leaf: bool
    position: int
    content: str
    metadata: dict = Field(default_factory=dict)
    embedding: list[float] | None = None


class Document(BaseModel):
    # The index being indexed; the document joins it in the same transaction.
    index_id: int | None = None
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

        # Replacing the document must not drop it from the other indexes it is in.
        member_of = [
            r["index_id"]
            for r in conn.execute(
                "SELECT x.index_id FROM index_documents x JOIN documents d ON d.id = x.document_id"
                " WHERE d.file_path = %s",
                (document.file_path,),
            )
        ]
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

        for index_id in {*member_of, document.index_id} - {None}:
            add_to_index(conn, index_id, document_id)

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
