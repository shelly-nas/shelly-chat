"""Configuration from the environment.

The model settings here are defaults the browser picks up through
GET /api/config: the browser talks to Ollama itself, the server never does.
"""

import os


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


SERVER_PORT = _int("SERVER_PORT", 3000)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _int("DB_PORT", 5432)
DB_USER = os.getenv("DB_USER", "chat")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "chat")

# Bearer token the indexer has to send to change the index. Empty means the
# index endpoints are open, which is only acceptable locally; the production
# and acc compose files refuse to start without it.
INDEX_TOKEN = os.getenv("INDEX_TOKEN", "")

# Retrieval
RETRIEVAL_TOP_K = _int("RETRIEVAL_TOP_K", 20)
CONTEXT_TOP_N = _int("CONTEXT_TOP_N", 5)
AUTOMERGE_THRESHOLD = _float("AUTOMERGE_THRESHOLD", 0.5)
QUERY_MAX_LENGTH = _int("QUERY_MAX_LENGTH", 2000)

# Generation defaults for the browser
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemma4:latest")
LLM_SYSTEM_PROMPT = os.getenv("LLM_SYSTEM_PROMPT", "You are a helpful assistant.")
NO_ANSWER_RESPONSE = os.getenv(
    "NO_ANSWER_RESPONSE", "I could not find this in the provided sources."
)
CHAT_HISTORY_MAX_TURNS = _int("CHAT_HISTORY_MAX_TURNS", 10)
LLM_TEMPERATURE = _float("LLM_TEMPERATURE", 1.0)
LLM_TOP_P = _float("LLM_TOP_P", 0.95)
LLM_TOP_K = _int("LLM_TOP_K", 64)
LLM_NUM_CTX = _int("LLM_NUM_CTX", 32000)
