"""The original documents, so a source in the chat can be opened.

Read-only and limited to supported documents inside the documents folder.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app import files

router = APIRouter(prefix="/api/files")

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
}


@router.get("/{file_path:path}")
def get_file(file_path: str):
    try:
        path = files.resolve(file_path)
    except files.PathError:
        raise HTTPException(status_code=404, detail="Document niet gevonden.")
    if not files.is_supported(path):
        raise HTTPException(status_code=404, detail="Document niet gevonden.")
    # PDFs open in the browser; Markdown and text show as plain text.
    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "text/plain; charset=utf-8")
    return FileResponse(path, media_type=media_type, filename=path.name, content_disposition_type="inline")
