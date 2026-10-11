"""Shared settings people change in the app, stored in app_settings.

Only the current value is kept; a missing row means the default from the
environment.
"""

from app import config

SYSTEM_PROMPT = "system_prompt"


def get(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else None


def put(conn, key: str, value: str | None) -> None:
    """Store a value; None goes back to the default."""
    if value is None:
        conn.execute("DELETE FROM app_settings WHERE key = %s", (key,))
    else:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (%s, %s)"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (key, value),
        )


def system_prompt(conn) -> str:
    return get(conn, SYSTEM_PROMPT) or config.LLM_SYSTEM_PROMPT
