"""Index GitLab documents into shelly-chat.

Runs on the machine with Ollama (and, if GitLab is behind a VPN, the VPN):
fetches wiki pages and repository files from GitLab, splits them into
hierarchical chunks, embeds the leaf chunks with the local Ollama, and stores
everything on the NAS through the server's /api/index endpoints. The NAS never
sees GitLab credentials and never runs a model.

Incremental sync: the NAS keeps a content_hash per document. Only new and
changed documents are re-embedded; unchanged ones are skipped and deleted ones
are removed from the index. A change of embedding model or chunk size resets
the index automatically, because old and new vectors do not mix. Use
--full-reindex to force a rebuild.

    python -m indexing.indexer
    python -m indexing.indexer --full-reindex
    python -m indexing.indexer --build-abbreviations
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core.schema import BaseNode, MetadataMode

from indexing.change_detection import classify_documents, compute_hash
from indexing.console import log_info, log_success, log_warn
from indexing.nas_client import NasClient
from indexing.ollama import OllamaEmbedder

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")


def _parse_url_list(raw: str) -> List[str]:
    """Split a comma-separated .env URL list, skipping blank entries and
    lines commented out with a leading '#' (e.g. GITLAB_WIKI_URLS with one
    URL disabled by prefixing it with '# ')."""
    return [
        u.strip()
        for u in raw.split(",")
        if u.strip() and not u.strip().startswith("#")
    ]


@dataclass
class IndexingConfig:
    server_url: str = "http://localhost:3000"
    index_token: str = ""
    embed_model: str = "qwen3-embedding:latest"
    ollama_base_url: str = "http://localhost:11434"
    embed_batch_size: int = 16
    parent_chunk_size: int = 1500
    parent_chunk_overlap: int = 300
    child_chunk_size: int = field(default=None)
    gitlab_pat: str = ""
    gitlab_wiki_urls: List[str] = field(default_factory=list)
    gitlab_repo_urls: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.child_chunk_size is None:
            self.child_chunk_size = self.parent_chunk_size // 4

        if self.child_chunk_size != self.parent_chunk_size // 4:
            log_warn(
                f"CHILD_CHUNK_SIZE ({self.child_chunk_size}) wijkt af van de standaard "
                f"LlamaIndex-verhouding van 1/4 (verwacht: {self.parent_chunk_size // 4} "
                f"op basis van PARENT_CHUNK_SIZE={self.parent_chunk_size}). "
                f"Dit kan leiden tot onbedoelde werking van het auto-mergen en verminderde "
                f"retrieval-kwaliteit."
            )

    @classmethod
    def from_env(cls) -> "IndexingConfig":
        parent_chunk_size = int(os.getenv("PARENT_CHUNK_SIZE", "1500"))
        return cls(
            server_url=os.getenv("SHELLY_CHAT_URL", "http://localhost:3000"),
            index_token=os.getenv("INDEX_TOKEN", ""),
            embed_model=os.getenv("EMBED_MODEL", "qwen3-embedding:latest"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            embed_batch_size=int(os.getenv("EMBED_BATCH_SIZE", "16")),
            parent_chunk_size=parent_chunk_size,
            parent_chunk_overlap=int(os.getenv("PARENT_CHUNK_OVERLAP", "300")),
            child_chunk_size=int(os.getenv("CHILD_CHUNK_SIZE", str(parent_chunk_size // 4))),
            gitlab_pat=os.getenv("GITLAB_PAT", ""),
            gitlab_wiki_urls=_parse_url_list(os.getenv("GITLAB_WIKI_URLS", "")),
            gitlab_repo_urls=_parse_url_list(os.getenv("GITLAB_REPO_URLS", "")),
        )

    def nas(self) -> NasClient:
        return NasClient(self.server_url, self.index_token)

    def embedder(self) -> OllamaEmbedder:
        return OllamaEmbedder(self.embed_model, self.ollama_base_url, self.embed_batch_size)


def _meta(config: IndexingConfig, dimensions: int) -> dict:
    """The config values that require a full reindex when they change."""
    return {
        "embed_model": config.embed_model,
        "embed_dimensions": dimensions,
        "parent_chunk_size": config.parent_chunk_size,
        "child_chunk_size": config.child_chunk_size,
        "parent_chunk_overlap": config.parent_chunk_overlap,
    }


def document_payload(doc: Document, config: IndexingConfig, embedder: OllamaEmbedder) -> dict:
    """Split one document into hierarchical chunks, embed the leaves, and
    shape it for PUT /api/index/documents."""
    node_parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=[config.parent_chunk_size, config.child_chunk_size]
    )
    all_nodes: List[BaseNode] = node_parser.get_nodes_from_documents([doc])
    leaves = get_leaf_nodes(all_nodes)
    leaf_ids = {n.node_id for n in leaves}

    # Embed what LlamaIndex would embed: the text plus the metadata that is
    # not excluded from embedding (title, file name, URL).
    vectors = embedder.embed([n.get_content(metadata_mode=MetadataMode.EMBED) for n in leaves])
    embedding_by_id = {n.node_id: v for n, v in zip(leaves, vectors)}

    nodes = []
    for position, node in enumerate(all_nodes):
        parent = node.parent_node
        nodes.append({
            "id": node.node_id,
            "parent_id": parent.node_id if parent else None,
            "is_leaf": node.node_id in leaf_ids,
            "position": position,
            "content": node.get_content(),
            "metadata": node.metadata,
            "embedding": embedding_by_id.get(node.node_id),
        })

    meta = doc.metadata
    return {
        "file_path": meta.get("file_path", ""),
        "file_name": meta.get("file_name", ""),
        "source_url": meta.get("source_url", meta.get("file_path", "")),
        "content_hash": meta["content_hash"],
        "content": doc.text,
        "metadata": meta,
        "nodes": nodes,
    }


def run_pipeline(
    documents: List[Document],
    config: IndexingConfig,
    full_reindex: bool = False,
) -> None:
    """Sync the fetched documents to the NAS index, incrementally."""
    if not documents:
        log_warn("Geen documenten om te indexeren.")
        return

    # Stamp content_hash on every document before parsing so it propagates to
    # every chunk's metadata. Exclude it from embed/LLM metadata so the hash
    # never pollutes the embedding input.
    for doc in documents:
        doc.metadata["content_hash"] = compute_hash(doc.text)
        doc.excluded_embed_metadata_keys.append("content_hash")
        doc.excluded_llm_metadata_keys.append("content_hash")

    nas = config.nas()
    embedder = config.embedder()

    current = nas.current_meta()
    if current and current["embed_model"] == config.embed_model:
        dimensions = current["embed_dimensions"]
    else:
        log_info(f"Embeddingmodel {config.embed_model} laden om de dimensie te bepalen ...")
        dimensions = embedder.dimensions()

    desired = _meta(config, dimensions)
    if not full_reindex and current is not None:
        drifted = [
            f"{k}: {current.get(k)} → {v}" for k, v in desired.items() if current.get(k) != v
        ]
        if drifted:
            log_warn(
                "Configuratie gewijzigd sinds laatste indexering "
                f"({'; '.join(drifted)}) — automatische volledige herindexering."
            )
            full_reindex = True

    if full_reindex:
        log_info("Volledige herindexering: de index op de NAS wordt geleegd ...")
    # Written before any document, so an interrupted rebuild resumes
    # incrementally instead of wiping again on the next run.
    nas.put_meta(desired, reset=full_reindex)

    indexed_hashes = {} if full_reindex else nas.indexed_hashes()
    new_docs, changed_docs, deleted_paths, unchanged_docs = classify_documents(
        documents, indexed_hashes
    )
    log_info(
        f"Sync-resultaat: {len(unchanged_docs)} ongewijzigd overgeslagen, "
        f"{len(new_docs)} nieuw, {len(changed_docs)} gewijzigd, "
        f"{len(deleted_paths)} verwijderd."
    )

    for path in deleted_paths:
        nas.delete_document(path)
    if deleted_paths:
        log_info(f"{len(deleted_paths)} verwijderd(e) document(en) opgeruimd uit de index.")

    to_index = new_docs + changed_docs
    if not to_index:
        log_success("Niets te embedden — index is up-to-date.")
        return

    log_info(f"Embedden en opslaan van {len(to_index)} document(en) ...")
    try:
        for i, doc in enumerate(to_index, 1):
            name = doc.metadata.get("file_name") or doc.metadata.get("file_path", "")
            result = nas.put_document(document_payload(doc, config, embedder))
            extra = f", {result['abbreviations']} afkorting(en)" if result["abbreviations"] else ""
            log_info(f"  [{i}/{len(to_index)}] {name}: {result['chunks']} chunks{extra}")
    finally:
        log_info(f"Embeddingmodel {config.embed_model} ontladen ...")
        try:
            embedder.unload()
        except Exception as exc:
            log_warn(f"Model ontladen mislukt — {exc}")

    log_success(f"Indexering voltooid. {len(to_index)} document(en) geïndexeerd.")


def fetch_all_documents(config: IndexingConfig, token: Optional[str] = None) -> List[Document]:
    """Fetch every configured GitLab wiki and repository in one pass.

    Collecting first and embedding afterwards loads the embedding model only
    once, however many sources there are.
    """
    from indexing.gitlab_repo_fetcher import fetch_repo_documents
    from indexing.gitlab_wiki_fetcher import fetch_wiki_documents

    pat = token or config.gitlab_pat
    if not pat:
        raise ValueError(
            "GITLAB_PAT is niet ingesteld. Zonder token geeft GitLab 404 op "
            "private projecten. Zet GITLAB_PAT in host/.env."
        )

    documents: List[Document] = []
    for url in config.gitlab_wiki_urls:
        log_info(f"Ophalen wiki: {url}")
        try:
            documents.extend(fetch_wiki_documents(url, token=pat))
        except ConnectionError:
            log_warn(
                f"Kan geen verbinding maken met GitLab ({url}). "
                "Controleer of de VPN is ingeschakeld en het URL correct is. "
                "Deze bron wordt overgeslagen."
            )
    for url in config.gitlab_repo_urls:
        log_info(f"Ophalen repo: {url}")
        try:
            documents.extend(fetch_repo_documents(url, token=pat))
        except ConnectionError:
            log_warn(
                f"Kan geen verbinding maken met GitLab ({url}). "
                "Controleer of de VPN is ingeschakeld en het URL correct is. "
                "Deze bron wordt overgeslagen."
            )

    log_info(f"Totaal opgehaalde documenten: {len(documents)}")
    return documents


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Indexeer GitLab-wiki's en -repositories in shelly-chat. Bronnen staan in "
            "GITLAB_WIKI_URLS en GITLAB_REPO_URLS in host/.env; de NAS in SHELLY_CHAT_URL."
        ),
    )
    parser.add_argument(
        "--gitlab-token",
        metavar="TOKEN",
        default=None,
        help="GitLab Personal Access Token; overschrijft GITLAB_PAT.",
    )
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        help=(
            "Leeg de index op de NAS en indexeer alles opnieuw. Een ander EMBED_MODEL of "
            "andere chunkgroottes worden automatisch herkend; dit forceert het."
        ),
    )
    parser.add_argument(
        "--build-abbreviations",
        action="store_true",
        help="Bouw de afkortingen opnieuw op uit de opgeslagen documenten, zonder te embedden.",
    )
    args = parser.parse_args()

    config = IndexingConfig.from_env()

    if args.build_abbreviations:
        result = config.nas().rebuild_abbreviations()
        log_success(
            f"Klaar. {result['abbreviations']} afkortingen uit {result['documents']} documenten."
        )
        return

    if not config.gitlab_wiki_urls and not config.gitlab_repo_urls:
        parser.print_help()
        raise SystemExit("\nFout: zet GITLAB_WIKI_URLS en/of GITLAB_REPO_URLS in host/.env.")

    documents = fetch_all_documents(config, token=args.gitlab_token)
    run_pipeline(documents, config, full_reindex=args.full_reindex)


if __name__ == "__main__":
    main()
