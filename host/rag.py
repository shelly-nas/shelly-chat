"""The browser's question-answering pipeline, in Python.

Same steps as client/src/lib/rag.ts: expand on the NAS, embed with the local
Ollama, retrieve on the NAS, generate with the local Ollama. Used by the
evaluation in tests/eval and handy for trying a question from the terminal:

    python rag.py "Mijn BV" "Hoe werkt het Renovate-proces?"
    python rag.py "Wat is RAG?"                 # zonder index, zonder bronnen
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

SHELLY_CHAT_URL = os.getenv("SHELLY_CHAT_URL", "http://localhost:3000").rstrip("/")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
# Like "Denken uitzetten" in the app (on by default there): LLM_THINK=true lets the model think first.
LLM_THINK = os.getenv("LLM_THINK", "false").lower() == "true"


def build_context_string(contexts: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {c['file_path']} (page {c['page_number']})\n{c['content']}"
        for i, c in enumerate(contexts)
    )


def build_qa_prompt(contexts: list[dict], query: str) -> str:
    sources = build_context_string(contexts) if contexts else "(geen relevante bronnen gevonden)"
    return f"BRONNEN:\n{sources}\n\nVRAAG: {query}\n\nANTWOORD:"


def index_id(name: str) -> int:
    """The id of a named index."""
    indexes = requests.get(f"{SHELLY_CHAT_URL}/api/indexes", timeout=10).json()["indexes"]
    for index in indexes:
        if index["name"].lower() == name.lower():
            return index["id"]
    raise RuntimeError(f"Er is geen index '{name}'. Er zijn: {', '.join(i['name'] for i in indexes) or 'geen'}.")


def search(question: str, idx: int, config: dict) -> tuple[str, list[dict], list[dict]]:
    """Expand, embed and retrieve in one index: (query, expansions, contexts)."""
    expanded = requests.post(
        f"{SHELLY_CHAT_URL}/api/expand", json={"query": question, "index_id": idx}, timeout=10
    ).json()
    query = expanded["query"]

    embedding = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": config["embed_model"], "input": [query], "keep_alive": 0},
        timeout=300,
    ).json()["embeddings"][0]

    resp = requests.post(
        f"{SHELLY_CHAT_URL}/api/retrieve",
        json={"embedding": embedding, "embed_model": config["embed_model"], "index_id": idx},
        timeout=60,
    )
    resp.raise_for_status()
    return query, expanded["expansions"], resp.json()["contexts"]


def ask(question: str, index: str | None = None, history: list[dict] | None = None, llm_model: str | None = None) -> dict:
    """Answer one question, with sources from the named index if there is one.

    Like the app: without an index, or when searching it fails, the model
    still answers, without sources ("Buiten de bronnen" in the system prompt).
    """
    history = history or []
    config = requests.get(f"{SHELLY_CHAT_URL}/api/config", timeout=10).json()
    model = llm_model or os.getenv("LLM_MODEL_NAME") or config["llm_model"]

    query, expansions, contexts, searched = question, [], [], False
    if index is not None and config["embed_model"]:
        try:
            query, expansions, contexts = search(question, index_id(index), config)
            searched = True
        except (requests.RequestException, KeyError, RuntimeError) as exc:
            print(f"Zoeken in de index lukte niet ({exc}); antwoord zonder bronnen.", file=sys.stderr)
    if searched and not contexts and not config["answer_without_sources"]:
        return {"answer": config["no_answer_response"], "contexts": [], "query": query,
                "expansions": expansions, "duration_s": 0.0, "model": model}

    system = config["system_prompt"].replace("{today}", date.today().isoformat())
    messages = [{"role": "system", "content": system}]
    messages += history[-config["history_max_turns"] * 2 :]
    messages.append({"role": "user", "content": build_qa_prompt(contexts, query)})

    start = time.perf_counter()
    answer, stats = [], {}
    with requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": True,
              # Like the app: the model stays loaded for the next question.
              "options": config["llm_options"], "think": LLM_THINK, "keep_alive": "10m"},
        stream=True,
        timeout=600,
    ) as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line:
                chunk = json.loads(line)
                answer.append(chunk.get("message", {}).get("content", ""))
                if chunk.get("done"):
                    stats = chunk
    return {
        "answer": "".join(answer),
        "contexts": contexts,
        "query": query,
        "expansions": expansions,
        "duration_s": round(time.perf_counter() - start, 2),
        "model": model,
        # Seconds and tokens as Ollama reports them, like the timings in the app.
        "timings": {
            "load_s": round(stats.get("load_duration", 0) / 1e9, 2),
            "prompt_tokens": stats.get("prompt_eval_count", 0),
            "prompt_s": round(stats.get("prompt_eval_duration", 0) / 1e9, 2),
            "output_tokens": stats.get("eval_count", 0),
            "output_s": round(stats.get("eval_duration", 0) / 1e9, 2),
        },
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('Gebruik: python rag.py ["Naam van de index"] "je vraag"')
    if len(sys.argv) == 2:
        result = ask(sys.argv[1])
    else:
        result = ask(" ".join(sys.argv[2:]), index=sys.argv[1])
    print(result["answer"])
    print()
    for c in result["contexts"]:
        print(f"[{c['source_num']}] {c['file_path']} ({c['similarity']:.2f}, {c['chunk_type']})")
