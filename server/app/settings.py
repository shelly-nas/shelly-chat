"""Shared settings people change in the app, stored in app_settings.

Every setting has a default from the environment (app/config.py). Only values
people changed are stored, and only the current one: a missing row means the
default, and resetting a setting deletes its row.
"""

import json
from dataclasses import dataclass

from app import config


@dataclass(frozen=True)
class Setting:
    type: type
    default: object
    min: float | None = None
    max: float | None = None
    max_length: int = 20_000


# The settings, by key. Groups match the sections of the Settings screen.
SETTINGS: dict[str, Setting] = {
    # Answers
    "system_prompt": Setting(str, config.LLM_SYSTEM_PROMPT),
    "no_answer_response": Setting(str, config.NO_ANSWER_RESPONSE, max_length=2_000),
    "llm_temperature": Setting(float, config.LLM_TEMPERATURE, 0, 2),
    "llm_top_p": Setting(float, config.LLM_TOP_P, 0, 1),
    "llm_top_k": Setting(int, config.LLM_TOP_K, 1, 1_000),
    "llm_num_ctx": Setting(int, config.LLM_NUM_CTX, 1_024, 1_048_576),
    "llm_max_tokens": Setting(int, config.LLM_MAX_TOKENS, 1, 1_048_576),
    "retrieval_top_k": Setting(int, config.RETRIEVAL_TOP_K, 1, 500),
    "context_top_n": Setting(int, config.CONTEXT_TOP_N, 1, 100),
    "automerge_threshold": Setting(float, config.AUTOMERGE_THRESHOLD, 0, 1),
    "history_max_turns": Setting(int, config.CHAT_HISTORY_MAX_TURNS, 0, 100),
    "query_max_length": Setting(int, config.QUERY_MAX_LENGTH, 100, 100_000),
    # Indexing: a change to the chunk sizes rebuilds every index.
    "parent_chunk_size": Setting(int, config.PARENT_CHUNK_SIZE, 100, 20_000),
    "child_chunk_size": Setting(int, config.CHILD_CHUNK_SIZE, 50, 20_000),
    "parent_chunk_overlap": Setting(int, config.PARENT_CHUNK_OVERLAP, 0, 10_000),
    "max_file_mb": Setting(int, config.MAX_FILE_MB, 1, 10_000),
}


class InvalidSetting(ValueError):
    pass


def validate(key: str, value: object) -> object:
    """The value as stored, or InvalidSetting with a message for people."""
    setting = SETTINGS.get(key)
    if setting is None:
        raise InvalidSetting(f"Onbekende instelling: {key}.")
    if setting.type is str:
        if not isinstance(value, str):
            raise InvalidSetting(f"{key} moet tekst zijn.")
        value = value.replace("\r\n", "\n").strip()
        if not value:
            raise InvalidSetting(f"{key} mag niet leeg zijn.")
        if len(value) > setting.max_length:
            raise InvalidSetting(f"{key} is langer dan {setting.max_length} tekens.")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSetting(f"{key} moet een getal zijn.")
    if setting.type is int:
        if value != int(value):
            raise InvalidSetting(f"{key} moet een geheel getal zijn.")
        value = int(value)
    else:
        value = float(value)
    if (setting.min is not None and value < setting.min) or (setting.max is not None and value > setting.max):
        raise InvalidSetting(f"{key} moet tussen {setting.min:g} en {setting.max:g} liggen.")
    return value


def _load(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return text  # an early system prompt, stored as plain text


def stored(conn) -> dict:
    """Only what people changed."""
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    return {r["key"]: _load(r["value"]) for r in rows if r["key"] in SETTINGS}


def current(conn) -> dict:
    """Every setting: the stored value, else the default."""
    values = stored(conn)
    return {key: values.get(key, s.default) for key, s in SETTINGS.items()}


def check(values: dict) -> None:
    """Rules between settings, on the values that would be in effect."""
    if values["child_chunk_size"] >= values["parent_chunk_size"]:
        raise InvalidSetting("De kleine chunks moeten kleiner zijn dan de grote.")
    if values["parent_chunk_overlap"] >= values["parent_chunk_size"]:
        raise InvalidSetting("De overlap moet kleiner zijn dan de grote chunks.")
    if values["context_top_n"] > values["retrieval_top_k"]:
        raise InvalidSetting("Er kunnen niet meer bronnen naar het model dan er kandidaten worden opgehaald.")
    if values["llm_max_tokens"] > values["llm_num_ctx"]:
        raise InvalidSetting("Een antwoord kan niet langer zijn dan het contextvenster.")


def update(conn, changes: dict) -> dict:
    """Apply {key: value}; None goes back to the default. All or nothing."""
    values = current(conn)
    clean = {}
    for key, value in changes.items():
        clean[key] = None if value is None else validate(key, value)
        values[key] = SETTINGS[key].default if value is None else clean[key]
    check(values)
    for key, value in clean.items():
        if value is None or value == SETTINGS[key].default:
            conn.execute("DELETE FROM app_settings WHERE key = %s", (key,))
        else:
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (%s, %s)"
                " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (key, json.dumps(value)),
            )
    return values


def chunk_config(values: dict) -> dict:
    return {k: values[k] for k in ("parent_chunk_size", "child_chunk_size", "parent_chunk_overlap")}
