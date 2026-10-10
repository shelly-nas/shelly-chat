"""Index the GitLab sources of shelly-chat from the command line.

The same run as the Index screen in the app (client/src/lib/indexer.ts), for
when a terminal or a scheduled job is handier than a browser tab. It runs on a
machine with Ollama (and the VPN to GitLab, if needed):

1. The sources come from the NAS (managed on the Index screen); the
   embedding model from EMBED_MODEL. A different model, dimension or chunk
   configuration than the index was built with resets the index.
2. Each document is fetched from GitLab and sent to the NAS, which extracts,
   hashes and splits it (POST /api/index/prepare). Unchanged documents stop
   there; for the others the leaf chunks are embedded with the local Ollama
   and stored (PUT /api/index/documents).
3. Documents gone from GitLab are removed - only when every source could be
   read, so an unreachable GitLab never empties the index.

    python -m indexing.indexer
    python -m indexing.indexer --full-reindex
    python -m indexing.indexer --build-abbreviations
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from indexing.console import log_error, log_info, log_success, log_warn
from indexing.nas_client import NasClient, NasError
from indexing.ollama import OllamaEmbedder
from indexing.source_document import Document

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")


@dataclass
class IndexingConfig:
    server_url: str = "http://localhost:3000"
    index_token: str = ""
    embed_model: str = "qwen3-embedding:latest"
    ollama_base_url: str = "http://localhost:11434"
    embed_batch_size: int = 16
    gitlab_pat: str = ""

    @classmethod
    def from_env(cls) -> "IndexingConfig":
        return cls(
            server_url=os.getenv("SHELLY_CHAT_URL", "http://localhost:3000"),
            index_token=os.getenv("INDEX_TOKEN", ""),
            embed_model=os.getenv("EMBED_MODEL", "qwen3-embedding:latest"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            embed_batch_size=int(os.getenv("EMBED_BATCH_SIZE", "16")),
            gitlab_pat=os.getenv("GITLAB_PAT", ""),
        )

    def nas(self) -> NasClient:
        return NasClient(self.server_url, self.index_token)

    def embedder(self) -> OllamaEmbedder:
        return OllamaEmbedder(self.embed_model, self.ollama_base_url, self.embed_batch_size)


def reset_reason(meta: Optional[dict], chunk_config: dict, embed_model: str, dimensions: int) -> Optional[str]:
    """Why the index must be rebuilt for this run, or None. Same rule as the app."""
    if not meta:
        return None
    if meta["embed_model"] != embed_model:
        return f"ander embeddingmodel ({meta['embed_model']} → {embed_model})"
    if meta["embed_dimensions"] != dimensions:
        return f"andere dimensie ({meta['embed_dimensions']} → {dimensions})"
    changed = [k for k, v in chunk_config.items() if meta.get(k) != v]
    return f"andere chunkinstellingen ({', '.join(changed)})" if changed else None


def store_document(doc: Document, nas: NasClient, embedder: OllamaEmbedder) -> Optional[dict]:
    """Prepare, embed and store one document. Returns the outcome, or None if unchanged."""
    meta = doc.metadata
    prepared = nas.prepare_document({
        "file_path": meta.get("file_path", ""),
        "file_name": meta.get("file_name", ""),
        "source_url": meta.get("source_url", meta.get("file_path", "")),
        "metadata": {k: v for k, v in meta.items() if k not in ("file_path", "file_name", "source_url")},
        "text": doc.text,
        "data_base64": doc.data_base64,
    })
    if prepared["status"] in ("unchanged", "empty"):
        return None

    document = prepared["document"]
    leaves = [n for n in document["nodes"] if n["is_leaf"]]
    vectors = embedder.embed([n["embed_text"] for n in leaves])
    by_id = {n["id"]: v for n, v in zip(leaves, vectors)}
    document["nodes"] = [
        {**{k: v for k, v in n.items() if k != "embed_text"}, "embedding": by_id.get(n["id"])}
        for n in document["nodes"]
    ]
    stored = nas.put_document(document)
    return {"status": prepared["status"], **stored}


def fetch_source(source: dict, token: str) -> List[Document]:
    from indexing.gitlab_repo_fetcher import fetch_repo_documents
    from indexing.gitlab_wiki_fetcher import fetch_wiki_documents

    if source["kind"] == "wiki":
        return fetch_wiki_documents(source["url"], token=token)
    return fetch_repo_documents(source["url"], token=token)


def run_pipeline(config: IndexingConfig, full_reindex: bool = False, token: Optional[str] = None) -> Dict[str, int]:
    counts = {"new": 0, "changed": 0, "unchanged": 0, "deleted": 0, "failed": 0}
    nas = config.nas()
    embedder = config.embedder()
    pat = token or config.gitlab_pat

    settings = nas.settings()
    if not settings["sources"]:
        raise SystemExit("Er staan nog geen bronnen op de NAS. Voeg ze toe op het scherm Index in de app.")

    # 1. Model, dimension and whether to start over
    meta = settings["meta"]
    if meta and meta["embed_model"] == config.embed_model:
        dimensions = meta["embed_dimensions"]
    else:
        log_info(f"Embeddingmodel {config.embed_model} laden om de dimensie te bepalen ...")
        dimensions = embedder.dimensions()
    reason = reset_reason(meta, settings["chunk_config"], config.embed_model, dimensions)
    if reason:
        log_warn(f"De index wordt opnieuw opgebouwd: {reason}.")
    reset = full_reindex or reason is not None
    nas.put_meta({"embed_model": config.embed_model, "embed_dimensions": dimensions}, reset=reset)
    indexed = {} if reset else nas.indexed_hashes()

    # 2. Fetch every source; collecting first loads the embedding model once.
    documents: List[Document] = []
    all_fetched = True
    for source in settings["sources"]:
        log_info(f"Ophalen: {source['url']}")
        try:
            documents.extend(fetch_source(source, pat))
        except (ConnectionError, PermissionError, ValueError) as exc:
            all_fetched = False
            log_error(f"{source['url']}: {exc} Deze bron wordt overgeslagen.")
    log_info(f"Totaal opgehaalde documenten: {len(documents)}")

    # 3. Prepare, embed and store
    seen = set()
    try:
        for i, doc in enumerate(documents, 1):
            name = doc.metadata.get("file_name") or doc.metadata.get("file_path", "")
            seen.add(doc.metadata.get("file_path", ""))
            try:
                outcome = store_document(doc, nas, embedder)
            except (NasError, RuntimeError) as exc:
                counts["failed"] += 1
                log_error(f"  [{i}/{len(documents)}] {name}: {exc}")
                continue
            if outcome is None:
                counts["unchanged"] += 1
                continue
            counts[outcome["status"]] += 1
            extra = f", {outcome['abbreviations']} afkorting(en)" if outcome["abbreviations"] else ""
            label = "nieuw" if outcome["status"] == "new" else "gewijzigd"
            log_info(f"  [{i}/{len(documents)}] {name}: {label}, {outcome['chunks']} chunks{extra}")

        # 4. Remove what is gone from GitLab
        gone = [path for path in indexed if path not in seen]
        if gone and not all_fetched:
            log_warn(f"{len(gone)} document(en) niet verwijderd: niet elke bron kon worden gelezen.")
        else:
            for path in gone:
                nas.delete_document(path)
                counts["deleted"] += 1
            if gone:
                log_info(f"{len(gone)} document(en) verwijderd die niet meer in GitLab staan.")
    finally:
        try:
            embedder.unload()
        except Exception as exc:
            log_warn(f"Model ontladen mislukt — {exc}")

    log_success(
        f"Klaar: {counts['new']} nieuw, {counts['changed']} gewijzigd, {counts['unchanged']} ongewijzigd, "
        f"{counts['deleted']} verwijderd, {counts['failed']} mislukt."
    )
    return counts


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Indexeer de GitLab-bronnen van shelly-chat. De bronnen staan op de NAS (scherm Index "
            "in de app); de NAS in SHELLY_CHAT_URL, je GitLab-token in GITLAB_PAT (host/.env)."
        ),
    )
    parser.add_argument("--gitlab-token", metavar="TOKEN", default=None, help="Overschrijft GITLAB_PAT.")
    parser.add_argument("--full-reindex", action="store_true", help="Leeg de index en indexeer alles opnieuw.")
    parser.add_argument(
        "--build-abbreviations",
        action="store_true",
        help="Bouw de afkortingen opnieuw op uit de opgeslagen documenten, zonder te embedden.",
    )
    args = parser.parse_args()
    config = IndexingConfig.from_env()

    if args.build_abbreviations:
        result = config.nas().rebuild_abbreviations()
        log_success(f"Klaar. {result['abbreviations']} afkortingen uit {result['documents']} documenten.")
        return
    if not (args.gitlab_token or config.gitlab_pat):
        raise SystemExit("Fout: GITLAB_PAT is niet ingesteld. Zet het in host/.env of geef --gitlab-token mee.")

    run_pipeline(config, full_reindex=args.full_reindex, token=args.gitlab_token)


if __name__ == "__main__":
    main()
