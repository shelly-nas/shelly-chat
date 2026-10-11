"""Conversation history. The browser saves each finished question and answer."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import db

router = APIRouter(prefix="/api/conversations")

TITLE_MAX_LENGTH = 80

# The index is part of every conversation; index_name is NULL once it is deleted.
_COLUMNS = "c.id, c.title, c.index_id, i.name AS index_name, c.created_at, c.updated_at"


def _title_from(text: str) -> str:
    title = " ".join(text.split())
    if len(title) > TITLE_MAX_LENGTH:
        title = title[: TITLE_MAX_LENGTH - 1].rstrip() + "…"
    return title or "Nieuw gesprek"


@router.get("")
def list_conversations(limit: int = 100):
    with db.connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM conversations c LEFT JOIN indexes i ON i.id = c.index_id"
            " ORDER BY c.updated_at DESC LIMIT %s",
            (min(max(limit, 1), 500),),
        ).fetchall()
    return {"conversations": rows}


class NewMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    effective_query: str | None = None
    expansions: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    model: str | None = None
    duration_ms: int | None = None


class CreateConversation(BaseModel):
    title: str | None = None
    # Chosen when the conversation starts; it can not be changed afterwards.
    index_id: int
    messages: list[NewMessage] = Field(default_factory=list)


def _insert_messages(conn, conversation_id: uuid.UUID, messages: list[NewMessage]) -> list[dict]:
    inserted = []
    for m in messages:
        inserted.append(
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, effective_query,"
                " expansions, sources, model, duration_ms)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                " RETURNING id, role, content, effective_query, expansions, sources,"
                " model, duration_ms, created_at",
                (
                    conversation_id,
                    m.role,
                    m.content,
                    m.effective_query,
                    Jsonb(m.expansions),
                    Jsonb(m.sources),
                    m.model,
                    m.duration_ms,
                ),
            ).fetchone()
        )
    return inserted


@router.post("", status_code=201)
def create_conversation(request: CreateConversation):
    first_user = next((m.content for m in request.messages if m.role == "user"), "")
    title = _title_from(request.title or first_user)
    with db.connection() as conn:
        if not conn.execute("SELECT 1 FROM indexes WHERE id = %s", (request.index_id,)).fetchone():
            raise HTTPException(status_code=422, detail="Deze index bestaat niet (meer).")
        created = conn.execute(
            "INSERT INTO conversations (title, index_id) VALUES (%s, %s) RETURNING id",
            (title, request.index_id),
        ).fetchone()
        conversation = _get(conn, created["id"])
        messages = _insert_messages(conn, conversation["id"], request.messages)
    return {**conversation, "messages": messages}


def _get(conn, conversation_id) -> dict:
    conversation = conn.execute(
        f"SELECT {_COLUMNS} FROM conversations c LEFT JOIN indexes i ON i.id = c.index_id WHERE c.id = %s",
        (conversation_id,),
    ).fetchone()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Gesprek niet gevonden.")
    return conversation


@router.get("/{conversation_id}")
def get_conversation(conversation_id: uuid.UUID):
    with db.connection() as conn:
        conversation = _get(conn, conversation_id)
        messages = conn.execute(
            "SELECT id, role, content, effective_query, expansions, sources, model,"
            " duration_ms, created_at FROM messages"
            " WHERE conversation_id = %s ORDER BY created_at, id",
            (conversation_id,),
        ).fetchall()
    return {**conversation, "messages": messages}


class AppendMessages(BaseModel):
    messages: list[NewMessage] = Field(min_length=1)


@router.post("/{conversation_id}/messages", status_code=201)
def append_messages(conversation_id: uuid.UUID, request: AppendMessages):
    with db.connection() as conn:
        updated = conn.execute(
            "UPDATE conversations SET updated_at = now() WHERE id = %s RETURNING id",
            (conversation_id,),
        ).fetchone()
        if updated is None:
            raise HTTPException(status_code=404, detail="Gesprek niet gevonden.")
        messages = _insert_messages(conn, conversation_id, request.messages)
    return {"messages": messages}


class RenameConversation(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.patch("/{conversation_id}")
def rename_conversation(conversation_id: uuid.UUID, request: RenameConversation):
    with db.connection() as conn:
        row = conn.execute(
            "UPDATE conversations SET title = %s WHERE id = %s RETURNING id",
            (request.title.strip(), conversation_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Gesprek niet gevonden.")
        return _get(conn, conversation_id)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: uuid.UUID):
    with db.connection() as conn:
        conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
    return Response(status_code=204)
