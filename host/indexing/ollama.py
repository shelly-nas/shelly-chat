"""Embeddings from the local Ollama (/api/embed)."""

from typing import List

import requests


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str, batch_size: int = 16, timeout: int = 300):
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.timeout = timeout

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            resp = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": batch},
                timeout=self.timeout,
            )
            if not resp.ok:
                raise RuntimeError(
                    f"Ollama embed met {self.model} mislukt ({resp.status_code}): {resp.text[:300]}"
                )
            vectors.extend(resp.json()["embeddings"])
        return vectors

    def dimensions(self) -> int:
        """Number of dimensions the model produces (loads the model once)."""
        return len(self.embed(["dimensie"])[0])

    def unload(self) -> None:
        """Free the model's memory right away instead of after Ollama's keep-alive."""
        requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": "", "keep_alive": 0},
            timeout=30,
        )
