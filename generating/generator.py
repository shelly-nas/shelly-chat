"""LlamaIndex Ollama LLM wrapper for the generating/ service.

Provides a pre-configured Ollama LLM instance used by the /api/chat
streaming handler in app.py.
"""

import os
from pathlib import Path
from llama_index.llms.ollama import Ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

def get_llm() -> Ollama:
    """Return a configured LlamaIndex Ollama LLM instance."""
    return Ollama(
        model=os.getenv("LLM_MODEL_NAME", "gemma4:latest"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "1.0")),
        context_window=int(os.getenv("LLM_MAX_TOKENS", "32000")),
        request_timeout=600.0,
        additional_kwargs={
            "top_p": float(os.getenv("LLM_TOP_P", "0.95")),
            "top_k": int(os.getenv("LLM_TOP_K", "64")),
        },
    )
