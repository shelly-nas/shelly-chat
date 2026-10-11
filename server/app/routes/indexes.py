"""Named indexes: what a conversation searches.

An index ("Mijn BV") has its own sources - folders or files in the documents
folder - and its own ignore patterns (gitignore syntax, kept in the database).
Which documents belong to it is recorded in index_documents while it is
indexed; the documents themselves are shared with other indexes.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app import db, files
from app.routes.index import require_token

router = APIRouter(prefix="/api/indexes")

_COLUMNS = "id, name, ignore_patterns, created_at, updated_at"


def _get(conn, index_id: int) -> dict:
    row = conn.execute(f"SELECT {_COLUMNS} FROM indexes WHERE id = %s", (index_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Index niet gevonden.")
    return row


def _sources(conn, index_id: int) -> list[dict]:
    return conn.execute(
        "SELECT id, path, created_at FROM index_sources WHERE index_id = %s ORDER BY path",
        (index_id,),
    ).fetchall()


def _source_info(row: dict, ignore_patterns: str) -> dict:
    """A source with whether it exists and how many documents it holds after ignoring."""
    found, missing = files.list_index_documents([row["path"]], ignore_patterns)
    return {**row, "exists": not missing, "documents": len(found)}


def remove_orphans(conn) -> int:
    """Delete documents that no index contains any more."""
    return conn.execute(
        "DELETE FROM documents d WHERE NOT EXISTS"
        " (SELECT 1 FROM index_documents x WHERE x.document_id = d.id)"
    ).rowcount


def _details(conn, index: dict) -> dict:
    stats = conn.execute(
        "SELECT count(*) AS documents, max(d.indexed_at) AS last_indexed_at"
        " FROM index_documents x JOIN documents d ON d.id = x.document_id WHERE x.index_id = %s",
        (index["id"],),
    ).fetchone()
    sources = [_source_info(s, index["ignore_patterns"]) for s in _sources(conn, index["id"])]
    return {**index, **stats, "sources": sources}


@router.get("")
def list_indexes():
    with db.connection() as conn:
        indexes = conn.execute(f"SELECT {_COLUMNS} FROM indexes ORDER BY lower(name)").fetchall()
        return {"indexes": [_details(conn, i) for i in indexes]}


@router.get("/{index_id}")
def get_index(index_id: int):
    with db.connection() as conn:
        return _details(conn, _get(conn, index_id))


class NewIndex(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.post("", status_code=201, dependencies=[Depends(require_token)])
def create_index(request: NewIndex):
    with db.connection() as conn:
        row = conn.execute(
            f"INSERT INTO indexes (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING {_COLUMNS}",
            (request.name.strip(),),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=409, detail="Er is al een index met deze naam.")
        return _details(conn, row)


class IndexChange(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    ignore_patterns: str | None = Field(default=None, max_length=20_000)


@router.patch("/{index_id}", dependencies=[Depends(require_token)])
def update_index(index_id: int, request: IndexChange):
    with db.connection() as conn:
        index = _get(conn, index_id)
        name = request.name.strip() if request.name is not None else index["name"]
        patterns = request.ignore_patterns if request.ignore_patterns is not None else index["ignore_patterns"]
        clash = conn.execute(
            "SELECT 1 FROM indexes WHERE lower(name) = lower(%s) AND id <> %s", (name, index_id)
        ).fetchone()
        if clash:
            raise HTTPException(status_code=409, detail="Er is al een index met deze naam.")
        row = conn.execute(
            f"UPDATE indexes SET name = %s, ignore_patterns = %s, updated_at = now() WHERE id = %s RETURNING {_COLUMNS}",
            (name, patterns.replace("\r\n", "\n"), index_id),
        ).fetchone()
        return _details(conn, row)


@router.delete("/{index_id}", status_code=204, dependencies=[Depends(require_token)])
def delete_index(index_id: int):
    """Conversations on it stay readable; documents only it held are removed."""
    with db.connection() as conn:
        _get(conn, index_id)
        conn.execute("DELETE FROM indexes WHERE id = %s", (index_id,))
        remove_orphans(conn)
    return Response(status_code=204)


class NewSource(BaseModel):
    # Relative to the documents folder; '' is the whole folder.
    path: str = Field(max_length=500)


@router.post("/{index_id}/sources", status_code=201, dependencies=[Depends(require_token)])
def add_source(index_id: int, request: NewSource):
    try:
        path = files.normalize(request.path)
        files.list_documents(path)
    except files.PathError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    with db.connection() as conn:
        index = _get(conn, index_id)
        row = conn.execute(
            "INSERT INTO index_sources (index_id, path) VALUES (%s, %s)"
            " ON CONFLICT (index_id, path) DO NOTHING RETURNING id, path, created_at",
            (index_id, path),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=409, detail="Deze bron staat al in de index.")
    return _source_info(row, index["ignore_patterns"])


@router.delete("/{index_id}/sources/{source_id}", status_code=204, dependencies=[Depends(require_token)])
def delete_source(index_id: int, source_id: int):
    """The documents leave the index at its next indexing run."""
    with db.connection() as conn:
        conn.execute("DELETE FROM index_sources WHERE id = %s AND index_id = %s", (source_id, index_id))
    return Response(status_code=204)


@router.get("/{index_id}/files", dependencies=[Depends(require_token)])
def list_files(index_id: int):
    """The documents an indexing run should cover, and the sources that could not be read."""
    with db.connection() as conn:
        index = _get(conn, index_id)
        sources = [s["path"] for s in _sources(conn, index_id)]
    found, missing = files.list_index_documents(sources, index["ignore_patterns"])
    return {"files": found, "missing": missing}


class Prune(BaseModel):
    # Every document the run found in the index's sources.
    keep: list[str]


@router.post("/{index_id}/prune", dependencies=[Depends(require_token)])
def prune(index_id: int, request: Prune):
    """End of a run: drop documents that left the index (deleted, ignored, or
    their source removed), then documents no index holds any more."""
    with db.connection() as conn:
        _get(conn, index_id)
        removed = conn.execute(
            "DELETE FROM index_documents x USING documents d"
            " WHERE x.document_id = d.id AND x.index_id = %s AND NOT (d.file_path = ANY(%s))",
            (index_id, request.keep),
        ).rowcount
        orphans = remove_orphans(conn)
    return {"removed": removed, "deleted_documents": orphans}
