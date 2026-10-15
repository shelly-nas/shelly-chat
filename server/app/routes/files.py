"""The original documents, so a source in the chat can be opened.

Read-only, without a token, and limited to documents that are indexed: the
documents folder on the NAS is the whole file system, and only what someone
put in an index is meant to be read through the app.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app import db, files

router = APIRouter(prefix="/api/files")

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("/{file_path:path}")
def get_file(file_path: str):
    try:
        relative = files.normalize(file_path)
        path = files.resolve(relative)
    except files.PathError:
        raise HTTPException(status_code=404, detail="Document niet gevonden.")
    with db.connection() as conn:
        indexed = conn.execute("SELECT 1 FROM documents WHERE file_path = %s", (relative,)).fetchone()
    if indexed is None or not files.is_supported(path):
        raise HTTPException(status_code=404, detail="Document niet gevonden.")
    # PDFs open in the browser; Markdown and text show as plain text.
    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "text/plain; charset=utf-8")
    return FileResponse(path, media_type=media_type, filename=path.name, content_disposition_type="inline")
