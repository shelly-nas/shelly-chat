"""The browser's question-answering pipeline, in Python.

Same steps as client/src/lib/rag.ts: expand on the NAS, embed with the local
Ollama, retrieve on the NAS, generate with the local Ollama. Used by the
evaluation in tests/eval and handy for trying a question from the terminal:

    python rag.py "Hoe werkt het Renovate-proces?"
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


def build_context_string(contexts: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {c['file_path']} (page {c['page_number']})\n{c['content']}"
        for i, c in enumerate(contexts)
    )


def build_qa_prompt(contexts: list[dict], query: str) -> str:
    return f"SOURCES:\n{build_context_string(contexts)}\n\nQUESTION: {query}\n\nANSWER:"


def ask(question: str, history: list[dict] | None = None, llm_model: str | None = None) -> dict:
    """Answer one question; returns answer, contexts, expansions and timing."""
    history = history or []
    config = requests.get(f"{SHELLY_CHAT_URL}/api/config", timeout=10).json()
    if not config["embed_model"]:
        raise RuntimeError("Er is nog niets geïndexeerd.")
    model = llm_model or os.getenv("LLM_MODEL_NAME") or config["llm_model"]

    expanded = requests.post(
        f"{SHELLY_CHAT_URL}/api/expand", json={"query": question}, timeout=10
    ).json()
    query = expanded["query"]

    embedding = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": config["embed_model"], "input": [query], "keep_alive": 0},
        timeout=300,
    ).json()["embeddings"][0]

    resp = requests.post(
        f"{SHELLY_CHAT_URL}/api/retrieve",
        json={"embedding": embedding, "embed_model": config["embed_model"]},
        timeout=60,
    )
    resp.raise_for_status()
    contexts = resp.json()["contexts"]
    if not contexts:
        return {"answer": config["no_answer_response"], "contexts": [], "query": query,
                "expansions": expanded["expansions"], "duration_s": 0.0, "model": model}

    system = config["system_prompt"].replace("{today}", date.today().isoformat())
    messages = [{"role": "system", "content": system}]
    messages += history[-config["history_max_turns"] * 2 :]
    messages.append({"role": "user", "content": build_qa_prompt(contexts, query)})

    start = time.perf_counter()
    answer = []
    with requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": True,
              "options": config["llm_options"], "keep_alive": 0},
        stream=True,
        timeout=600,
    ) as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line:
                answer.append(json.loads(line).get("message", {}).get("content", ""))
    return {
        "answer": "".join(answer),
        "contexts": contexts,
        "query": query,
        "expansions": expanded["expansions"],
        "duration_s": round(time.perf_counter() - start, 2),
        "model": model,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('Gebruik: python rag.py "je vraag"')
    result = ask(" ".join(sys.argv[1:]))
    print(result["answer"])
    print()
    for c in result["contexts"]:
        print(f"[{c['source_num']}] {c['file_path']} ({c['similarity']:.2f}, {c['chunk_type']})")
