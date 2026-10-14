"""What an embedding model needs around the text it embeds.

Some models are trained with an instruction in front of the *question* (not
the documents): Qwen3-Embedding expects "Instruct: <task>\\nQuery: <question>".
Without it the question vector is weaker and search finds less. The browser
and host/rag.py get the prefix through GET /api/config, so both embed the
question the same way.
"""

QWEN3_TASK = "Given a question, retrieve passages from documents that answer the question"


def query_prefix(model: str | None) -> str:
    """Text to put before a question when embedding it with `model`."""
    name = (model or "").split(":")[0].split("/")[-1].lower()
    if name.startswith("qwen3-embedding"):
        return f"Instruct: {QWEN3_TASK}\nQuery: "
    return ""
