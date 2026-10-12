"""Shared settings: how answers are made and documents are indexed.

They apply to everyone, so changing them needs the index token. Reading them
does not: the browser needs them to answer a question.
"""

from fastapi import APIRouter, Depends, HTTPException

from app import db, settings
from app.routes.index import require_token

router = APIRouter(prefix="/api/settings")


def _response(values: dict, stored: dict) -> dict:
    return {
        "values": values,
        "defaults": {key: s.default for key, s in settings.SETTINGS.items()},
        "changed": sorted(stored),
    }


@router.get("")
def get_settings():
    with db.connection() as conn:
        return _response(settings.current(conn), settings.stored(conn))


@router.put("", dependencies=[Depends(require_token)])
def put_settings(changes: dict[str, object]):
    """{key: value} for the settings to change; null goes back to the default."""
    with db.connection() as conn:
        try:
            values = settings.update(conn, changes)
        except settings.InvalidSetting as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return _response(values, settings.stored(conn))
