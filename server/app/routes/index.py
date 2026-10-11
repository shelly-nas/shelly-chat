"""The document index: files from the documents folder on the NAS.

Indexing is driven from where Ollama runs - the Index screen in the browser,
or the CLI in host/. Either one asks for the list of files in the sources
(GET /api/index/files), has each one read, hashed and split here (POST
/api/index/prepare), embeds the leaf chunks with its own Ollama, and stores
the result with PUT /api/index/documents. Everything but the GET summaries
needs the INDEX_TOKEN as a bearer token.

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
            " (SELECT max(indexed_at) FROM documents) AS last_indexed_at"
        ).fetchone()
    return {"meta": meta, **counts}


def _source_info(row: dict) -> dict:
    """A source with whether it exists and how many documents it holds now."""
    try:
        count, exists = len(files.list_documents(row["path"])), True
    except files.PathError:
        count, exists = 0, False
    return {**row, "exists": exists, "documents": count}


@router.get("/settings")
def index_settings():
    """What an indexing run needs to know up front: chunking and sources."""
    with db.connection() as conn:
        meta = conn.execute(f"SELECT {_META_COLUMNS} FROM index_meta").fetchone()
        sources = conn.execute(
            "SELECT id, path, created_at FROM index_sources ORDER BY path"
        ).fetchall()
    return {
        "meta": meta,
        "chunk_config": documents.chunk_config(),
        "documents_dir": config.DOCUMENTS_DIR,
        "documents_root_exists": files.root().is_dir(),
        "sources": [_source_info(s) for s in sources],
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


class NewSource(BaseModel):
    # Relative to the documents folder; '' is the whole folder.
    path: str = Field(max_length=500)


@router.post("/sources", status_code=201, dependencies=[Depends(require_token)])
def add_source(request: NewSource):
    try:
        path = files.normalize(request.path)
        files.list_documents(path)
    except files.PathError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    with db.connection() as conn:
        row = conn.execute(
            "INSERT INTO index_sources (path) VALUES (%s)"
            " ON CONFLICT (path) DO NOTHING RETURNING id, path, created_at",
            (path,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=409, detail="Deze bron staat er al.")
    return _source_info(row)


@router.get("/files", dependencies=[Depends(require_token)])
def list_files():
    """Every document in the sources, plus the sources that could not be read.

    The caller only removes documents that are gone when `missing` is empty:
    a folder that is (temporarily) unavailable must not empty the index.
    """
    with db.connection() as conn:
        sources = [r["path"] for r in conn.execute("SELECT path FROM index_sources ORDER BY path")]
    found: dict[str, None] = {}
    missing = []
    for source in sources:
        try:
            for path in files.list_documents(source):
                found[path] = None
        except files.PathError:
            missing.append(source)
    return {"files": list(found), "missing": missing}


@router.delete("/sources/{source_id}", status_code=204, dependencies=[Depends(require_token)])
def delete_source(source_id: int):
    with db.connection() as conn:
        conn.execute("DELETE FROM index_sources WHERE id = %s", (source_id,))
    return Response(status_code=204)


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


class PrepareRequest(BaseModel):
    file_path: str = Field(min_length=1)


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
            "SELECT content_hash FROM documents WHERE file_path = %s", (file_path,)
        ).fetchone()
    if stored and stored["content_hash"] == hash_:
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
