"""Shared settings: the system prompt every conversation uses."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import config, db, settings

router = APIRouter(prefix="/api/settings")


def _current(conn) -> dict:
    stored = settings.get(conn, settings.SYSTEM_PROMPT)
    return {
        "system_prompt": stored or config.LLM_SYSTEM_PROMPT,
        "system_prompt_is_default": stored is None,
        "default_system_prompt": config.LLM_SYSTEM_PROMPT,
    }


@router.get("")
def get_settings():
    with db.connection() as conn:
        return _current(conn)


class SettingsChange(BaseModel):
    # Empty or null goes back to LLM_SYSTEM_PROMPT. {today} becomes the date.
    system_prompt: str | None = Field(default=None, max_length=20_000)


@router.put("")
def put_settings(request: SettingsChange):
    prompt = (request.system_prompt or "").strip()
    with db.connection() as conn:
        settings.put(conn, settings.SYSTEM_PROMPT, prompt or None)
        return _current(conn)
