"""LlamaIndex-based document ingestion pipeline.

Fetches content from GitLab (wiki pages or repository files) via the GitLab
REST API and indexes it into Qdrant + SimpleDocumentStore.

Pipeline: HierarchicalNodeParser → OllamaEmbedding → Qdrant (child vectors)
          + SimpleDocumentStore (all nodes).

Incremental sync: on each run only new and changed documents are re-embedded.
Unchanged documents are skipped entirely (no embedding calls). Deleted
documents are removed from Qdrant and docstore automatically. Change detection
lives in Qdrant point payloads (content_hash + file_path) — there is no
manifest file; Qdrant is the single source of truth.

A version stamp in the `index_meta` Qdrant collection records the embed model
and chunk config the index was built with; config drift triggers an automatic
full reindex. Use --full-reindex to force one on demand.
"""

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv
from indexing.change_detection import (
    classify_documents,
    compute_hash,
    fetch_indexed_hashes,
)
from indexing.cleanup import cleanup_file_path
from indexing.console import log_info, log_success, log_warn
from indexing.lock import indexing_lock, lock_path_for
from indexing.version_stamp import delete_stamp, read_stamp, write_stamp
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

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
    qdrant_url: str = "http://localhost:6333"
    qdrant_child_collection: str = "chunks_child"
    embed_model: str = "qwen3-embedding:latest"
    ollama_base_url: str = "http://localhost:11434"
    docstore_path: str = "vector-db/docstore.json"
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
                f"Dit kan leiden tot onbedoelde werking van AutoMergingRetriever en verminderde "
                f"retrieval-kwaliteit. De standaard 1/4-verhouding is de aanbevolen LlamaIndex-instelling."
            )

    abbreviations_path: str = "vector-db/abbreviations.json"

    @classmethod
    def from_env(cls) -> "IndexingConfig":
        parent_chunk_size = int(os.getenv("PARENT_CHUNK_SIZE", "1500"))
        wiki_urls_str = os.getenv("GITLAB_WIKI_URLS", "")
        repo_urls_str = os.getenv("GITLAB_REPO_URLS", "")
        return cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_child_collection=os.getenv("QDRANT_CHILD_COLLECTION", "chunks_child"),
            embed_model=os.getenv("EMBED_MODEL", "qwen3-embedding:latest"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            docstore_path=os.getenv("DOCSTORE_PATH", "vector-db/docstore.json"),
            abbreviations_path=os.getenv("ABBREVIATIONS_PATH", "vector-db/abbreviations.json"),
            parent_chunk_size=parent_chunk_size,
            parent_chunk_overlap=int(os.getenv("PARENT_CHUNK_OVERLAP", "300")),
            child_chunk_size=int(os.getenv("CHILD_CHUNK_SIZE", str(parent_chunk_size // 4))),
            gitlab_pat=os.getenv("GITLAB_PAT", ""),
            gitlab_wiki_urls=_parse_url_list(wiki_urls_str),
            gitlab_repo_urls=_parse_url_list(repo_urls_str),
        )


# Pattern A: ABBREV (Full Term) — e.g. "VI (Versleutelde Identiteit)"
_ABBREV_THEN_TERM = re.compile(r'\b([A-Z][A-Za-z0-9]{1,7})\s*\(([^)]{3,80})\)')
# Pattern B: Full Term (ABBREV) — e.g. "Versleutelde Identiteit (VI)"
# Captures up to 4 words starting at a capital-letter boundary before the parenthesis.
_TERM_THEN_ABBREV = re.compile(
    r'(?<![A-Za-z])'
    r'([A-Z][a-zA-Z]*(?:\s+[a-zA-Z]+){0,3})'
    r'\s*\(([A-Z][A-Za-z0-9]{1,7})\)'
)
# Guard: abbreviation must contain ≥2 uppercase letters
_MIN_UPPER = re.compile(r'[A-Z].*[A-Z]')

def _build_stop_words() -> set:
    try:
        import nltk
        from nltk.corpus import stopwords as _sw
        try:
            return set(_sw.words("dutch")) | set(_sw.words("english"))
        except LookupError:
            nltk.download("stopwords", quiet=True)
            return set(_sw.words("dutch")) | set(_sw.words("english"))
    except ImportError:
        return set()


_STOP_WORDS: set = _build_stop_words()


def _strip_term(term: str) -> str:
    """Strip leading stop words (articles, prepositions) that are never part of an abbreviation."""
    words = term.split()
    while words and words[0].lower() in _STOP_WORDS:
        words = words[1:]
    return " ".join(words)


def _word_boundary_letters(word: str) -> list:
    """Return (letter_upper, char_pos) at word-initial and CamelCase boundaries."""
    result = [(word[0].upper(), 0)]
    for i in range(1, len(word)):
        ch = word[i]
        if ch.isupper():
            if word[i - 1].islower() or (i + 1 < len(word) and word[i + 1].islower()):
                result.append((ch.upper(), i))
    return result


def _is_valid_abbreviation(abbrev: str, term: str) -> bool:
    """Validate that abbrev is a genuine abbreviation of term.

    - Rejects if abbrev appears literally in the term.
    - Strips leading articles/prepositions before validation.
    - Uppercase letters must match word-initial or CamelCase boundary letters in order.
    - Words can only be skipped if their boundary letter is not needed.
    - After a boundary match, remaining letters of that word are available intra-word
      (only when the letter does not appear as a future boundary).
    - Single-word terms with intra-word matches require matched positions to span
      >50% of the word (rejects single-morpheme false positives like PRD/productie).
    - Mixed-case abbreviations require at least one intra-word match.
    - Words consumed must not exceed the number of uppercase letters.
    - Lowercase connectors must appear as a subsequence in the term.
    """
    if re.search(r"\b" + re.escape(abbrev) + r"\b", term):
        return False

    term = _strip_term(term)
    if not term:
        return False

    words = term.split()
    upper_letters = [c for c in abbrev if c.isupper()]
    lower_connectors = [c.lower() for c in abbrev if c.islower()]

    if len(upper_letters) < 2:
        return False

    boundaries: list = []
    for wi, word in enumerate(words):
        for letter, cp in _word_boundary_letters(word):
            boundaries.append((wi, letter, cp))

    ipos = 0
    last_wi = -1
    last_char_pos = -1
    words_used: set = set()
    intra_count = 0

    for letter in upper_letters:
        saved = ipos
        found = False
        remaining_upper = upper_letters[upper_letters.index(letter):]

        # Priority 1: boundary match — skip only words whose letter is not needed
        while ipos < len(boundaries):
            wi, ch, cp = boundaries[ipos]
            if wi < last_wi:
                ipos += 1
                continue
            if ch == letter:
                words_used.add(wi)
                last_wi = wi
                last_char_pos = cp
                ipos += 1
                found = True
                break
            if ch in remaining_upper[1:]:
                break
            ipos += 1

        if found:
            continue

        ipos = saved

        # Priority 2: intra-word, only if letter absent from future boundaries
        future = {ch for wi2, ch, _ in boundaries if wi2 > last_wi}
        if letter not in future and last_wi >= 0:
            word = words[last_wi]
            for ip in range(last_char_pos + 1, len(word)):
                if word[ip].upper() == letter:
                    last_char_pos = ip
                    intra_count += 1
                    found = True
                    break

        if not found:
            return False

    if len(words_used) > len(upper_letters):
        return False

    if lower_connectors and intra_count == 0:
        return False

    # Single-word intra-word: matched positions must span >50% of the word
    if intra_count > 0 and len(words) == 1:
        word = words[0]
        positions = []
        pos = 0
        for letter in upper_letters:
            idx = word.upper().find(letter, pos)
            if idx == -1:
                return False
            positions.append(idx)
            pos = idx + 1
        span = (positions[-1] - positions[0]) / max(len(word) - 1, 1)
        if span < 0.5:
            return False

    if lower_connectors:
        term_lower = term.lower()
        pos = 0
        for lc in lower_connectors:
            idx = term_lower.find(lc, pos)
            if idx == -1:
                return False
            pos = idx + 1

    return True


def _extract_abbreviations(text: str, metadata: dict) -> list:
    """Extract validated inline abbreviation definitions from document text.

    Finds both 'ABBREV (Full Term)' and 'Full Term (ABBREV)' patterns, then
    validates each pair using initialism/subsequence rules before keeping it.
    """
    source_url = metadata.get("source_url", metadata.get("file_path", ""))
    file_name = metadata.get("file_name", "")
    entries = []
    seen: set = set()

    def _add(abbrev: str, term: str, match_start: int, match_end: int) -> None:
        if not _MIN_UPPER.search(abbrev):
            return
        if not _is_valid_abbreviation(abbrev, term):
            return
        term = _strip_term(term)  # store clean term without leading stop words
        if not term:
            return
        key = (abbrev, term, source_url)
        if key in seen:
            return
        seen.add(key)
        start = max(0, match_start - 60)
        end = min(len(text), match_end + 60)
        snippet = (
            ("..." if start > 0 else "")
            + text[start:end].replace("\n", " ")
            + ("..." if end < len(text) else "")
        )
        entries.append({
            "abbrev": abbrev,
            "term": term,
            "source_url": source_url,
            "file_name": file_name,
            "snippet": snippet,
        })

    for match in _ABBREV_THEN_TERM.finditer(text):
        _add(match.group(1), match.group(2).strip(), match.start(), match.end())

    # For Pattern B: keep only the last match per (end-position) to avoid sentence prefixes
    b_by_end: dict = {}
    for match in _TERM_THEN_ABBREV.finditer(text):
        b_by_end[match.end()] = match
    for match in b_by_end.values():
        _add(match.group(2), match.group(1).strip(), match.start(), match.end())

    return entries


def _update_abbreviations_file(new_entries: list, source_urls: list, path: Path) -> None:
    """Merge new abbreviation entries into the abbreviations file.

    Removes any existing entries for the given source_urls first, then
    appends the new entries. This ensures re-indexing a document replaces
    its old abbreviations.
    """
    existing: list = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []

    url_set = set(source_urls)
    existing = [e for e in existing if e.get("source_url") not in url_set]
    existing.extend(new_entries)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_abbreviations_for_sources(source_urls: list, path: Path) -> None:
    """Remove all abbreviation entries belonging to the given source URLs."""
    if not path.exists():
        return
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    url_set = set(source_urls)
    filtered = [e for e in existing if e.get("source_url") not in url_set]
    path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_docstore(config: IndexingConfig) -> SimpleDocumentStore:
    docstore_path = Path(config.docstore_path)
    return (
        SimpleDocumentStore.from_persist_path(str(docstore_path))
        if docstore_path.exists()
        else SimpleDocumentStore()
    )


def _do_full_reindex_reset(config: IndexingConfig, qdrant_client: QdrantClient) -> None:
    """Drop Qdrant collections and delete local files for a clean slate."""
    collections = {c.name for c in qdrant_client.get_collections().collections}
    if config.qdrant_child_collection in collections:
        qdrant_client.delete_collection(config.qdrant_child_collection)
        log_info(f"Qdrant-collectie '{config.qdrant_child_collection}' verwijderd.")

    # Drop the version stamp together with the data so a crash between reset
    # and the fresh stamp write can never leave a stale stamp behind.
    delete_stamp(qdrant_client)

    docstore_path = Path(config.docstore_path)
    abbrev_path = Path(config.abbreviations_path)
    legacy_manifest = docstore_path.parent / "index-manifest.json"
    for path in [docstore_path, abbrev_path, legacy_manifest]:
        if path.exists():
            path.unlink()
            log_info(f"Verwijderd: {path}")


def _persist_docstore_atomic(docstore: SimpleDocumentStore, docstore_path: Path) -> None:
    """Persist the docstore via a temp file + rename so readers never see a torn file."""
    docstore_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=docstore_path.parent, suffix=".tmp")
    os.close(fd)
    try:
        docstore.persist(tmp_path)
        os.replace(tmp_path, docstore_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _embed_and_upsert(
    documents: List[Document],
    config: IndexingConfig,
    qdrant_client: QdrantClient,
    docstore: SimpleDocumentStore,
    abbreviations_path: Optional[Path] = None,
) -> None:
    """Parse, embed, and upsert a list of documents.

    Persists the docstore after each document so a crash leaves a consistent,
    recoverable state; the Qdrant upsert itself durably records each document's
    content_hash payload, so no separate change-tracking write is needed.
    """
    if not documents:
        return

    docstore_path = Path(config.docstore_path)
    chunk_sizes = [config.parent_chunk_size, config.child_chunk_size]
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=chunk_sizes)

    embed_model = OllamaEmbedding(
        model_name=config.embed_model,
        base_url=config.ollama_base_url,
    )
    Settings.embed_model = embed_model
    Settings.llm = None

    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=config.qdrant_child_collection,
    )
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
        docstore=docstore,
    )

    log_info(f"Embedden en upserten van {len(documents)} document(en) ...")

    try:
        from generating import indexing_runner
        indexing_runner.set_progress(0, len(documents))
    except Exception:
        pass

    for i, doc in enumerate(documents):
    try:
        from generating import indexing_runner
        indexing_runner.set_progress(0, len(documents))
    except Exception:
        pass

    for i, doc in enumerate(documents):
        all_nodes = node_parser.get_nodes_from_documents([doc])
        leaf_nodes = get_leaf_nodes(all_nodes)

        storage_context.docstore.add_documents(all_nodes)

        VectorStoreIndex(
            nodes=leaf_nodes,
            storage_context=storage_context,
            show_progress=True,
        )

        _persist_docstore_atomic(storage_context.docstore, docstore_path)

        try:
            from generating import indexing_runner
            indexing_runner.set_progress(i + 1, len(documents))
        except Exception:
            pass

        if abbreviations_path is not None:
            abbrev_entries = _extract_abbreviations(doc.text, doc.metadata)
            if abbrev_entries:
                source_url = doc.metadata.get("source_url", doc.metadata.get("file_path", ""))
                _update_abbreviations_file(abbrev_entries, [source_url], abbreviations_path)
                log_info(f"  {len(abbrev_entries)} afkorting(en) opgeslagen uit {doc.metadata.get('file_name', '')}")

    log_info(f"Embedding model {config.embed_model} ontladen ...")
    try:
        # Unload via the Ollama HTTP API (keep_alive=0). The `ollama` CLI is
        # not available inside the Docker container — Ollama runs on the host.
        base_url = config.ollama_base_url
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        requests.post(
            f"{base_url}/api/generate",
            json={"model": config.embed_model, "keep_alive": 0, "prompt": ""},
            timeout=30,
        )
        log_success("Model ontladen.")
    except Exception as exc:
        log_warn(f"Model ontladen mislukt — {exc}")


def _config_stamp(config: IndexingConfig) -> dict:
    """The config values that require a full reindex when they change."""
    return {
        "embed_model": config.embed_model,
        "parent_chunk_size": config.parent_chunk_size,
        "child_chunk_size": config.child_chunk_size,
        "parent_chunk_overlap": config.parent_chunk_overlap,
    }


def _run_pipeline(
    documents: List[Document],
    config: IndexingConfig,
    full_reindex: bool = False,
) -> None:
    """Core pipeline with incremental sync support.

    Shared by all ingestion modes (wiki, repo, all-sources). Holds an
    exclusive lock on vector-db/.indexing.lock for the whole run so a
    concurrent CLI run or docstore reload never races on the same files.
    """
    if not documents:
        log_warn("Geen documenten om te indexeren.")
        return

    # Stamp content_hash on every document before parsing so it propagates to
    # every Qdrant point payload. Exclude it from embed/LLM metadata so the
    # hash never pollutes the embedding input.
    for doc in documents:
        doc.metadata["content_hash"] = compute_hash(doc.text)
        doc.excluded_embed_metadata_keys.append("content_hash")
        doc.excluded_llm_metadata_keys.append("content_hash")

    with indexing_lock(lock_path_for(config.docstore_path), exclusive=True):
        qdrant_client = QdrantClient(url=config.qdrant_url)

        current_stamp = _config_stamp(config)
        stored_stamp = read_stamp(qdrant_client)
        if not full_reindex and stored_stamp is not None and stored_stamp != current_stamp:
            drifted = [
                f"{k}: {stored_stamp.get(k)} → {v}"
                for k, v in current_stamp.items()
                if stored_stamp.get(k) != v
            ]
            log_warn(
                "Configuratie gewijzigd sinds laatste indexering "
                f"({'; '.join(drifted)}) — automatische volledige herindexering."
            )
            full_reindex = True

        if full_reindex:
            log_info("Volledige herindexering gestart ...")
            _do_full_reindex_reset(config, qdrant_client)
            # Write the stamp immediately so an interrupted rebuild resumes
            # incrementally instead of wiping again on the next run.
            write_stamp(qdrant_client, current_stamp)
            docs_to_index = documents
            docs_to_cleanup: List[Document] = []
            deleted_paths: List[str] = []
        else:
            indexed_hashes = fetch_indexed_hashes(
                qdrant_client, config.qdrant_child_collection
            )
            new_docs, changed_docs, deleted_paths, unchanged_docs = classify_documents(
                documents, indexed_hashes
            )

            log_info(
                f"Sync-resultaat: {len(unchanged_docs)} ongewijzigd overgeslagen, "
                f"{len(new_docs)} nieuw, {len(changed_docs)} gewijzigd, "
                f"{len(deleted_paths)} verwijderd."
            )

            docs_to_index = new_docs + changed_docs
            docs_to_cleanup = changed_docs

            if stored_stamp is None:
                write_stamp(qdrant_client, current_stamp)

            if not docs_to_index and not deleted_paths:
                log_success("Niets te doen — index is up-to-date.")
                return

        docstore = _load_docstore(config)
        docstore_path = Path(config.docstore_path)
        abbreviations_path = Path(config.abbreviations_path)

        # Remove stale vectors and nodes before re-indexing or for deleted files.
        paths_to_cleanup = (
            [doc.metadata.get("file_path", "") for doc in docs_to_cleanup] + deleted_paths
        )
        # Abbreviations are keyed by source_url, which may differ from file_path for repo docs.
        source_urls_to_cleanup = (
            [doc.metadata.get("source_url", doc.metadata.get("file_path", "")) for doc in docs_to_cleanup]
            + deleted_paths
        )
        if paths_to_cleanup:
            log_info(f"Opruimen van {len(paths_to_cleanup)} verouderd(e) bestand(en) ...")
            for fp in paths_to_cleanup:
                cleanup_file_path(qdrant_client, config.qdrant_child_collection, docstore, fp)

            _remove_abbreviations_for_sources(source_urls_to_cleanup, abbreviations_path)

            _persist_docstore_atomic(docstore, docstore_path)

        if docs_to_index:
            _embed_and_upsert(
                docs_to_index, config, qdrant_client, docstore,
                abbreviations_path=abbreviations_path,
            )
        elif deleted_paths:
            log_success(f"{len(deleted_paths)} verwijderd(e) bestand(en) opgeruimd uit index.")
            return

    log_success(
        f"Indexering voltooid. {len(docs_to_index)} document(en) geïndexeerd in "
        f"Qdrant-collectie '{config.qdrant_child_collection}'."
    )


def run_gitlab_wiki_pipeline(
    wiki_url: str,
    token: Optional[str] = None,
    config: Optional[IndexingConfig] = None,
    full_reindex: bool = False,
) -> None:
    """Fetch all markdown pages from a GitLab wiki and index them.

    Each indexed document stores the direct GitLab wiki URL as ``source_url``
    metadata so the frontend can link back to the original page.
    """
    from indexing.gitlab_wiki_fetcher import fetch_wiki_documents

    if config is None:
        config = IndexingConfig.from_env()
    pat = token or config.gitlab_pat

    documents = fetch_wiki_documents(wiki_url=wiki_url, token=pat)
    _run_pipeline(documents, config, full_reindex=full_reindex)


def run_gitlab_repo_pipeline(
    repo_url: str,
    token: Optional[str] = None,
    path_filter: Optional[str] = None,
    branch: Optional[str] = None,
    config: Optional[IndexingConfig] = None,
    full_reindex: bool = False,
) -> None:
    """Fetch supported documents from a GitLab repository and index them.

    Supported file types: .md, .adoc, .pdf, .docx, .doc
    Each indexed document stores a direct GitLab blob URL as ``source_url``
    metadata so the frontend can link back to the original file.
    """
    from indexing.gitlab_repo_fetcher import fetch_repo_documents

    if config is None:
        config = IndexingConfig.from_env()
    pat = token or config.gitlab_pat

    documents = fetch_repo_documents(
        repo_url=repo_url,
        token=pat,
        path_filter=path_filter,
        branch=branch,
    )
    _run_pipeline(documents, config, full_reindex=full_reindex)


def run_all_sources_pipeline(
    token: Optional[str] = None,
    config: Optional[IndexingConfig] = None,
    full_reindex: bool = False,
) -> None:
    """Fetch all configured GitLab sources and index them in one pass.

    Collects documents from every GITLAB_WIKI_URLS and GITLAB_REPO_URLS entry
    first, then runs a single incremental sync cycle. This loads the embedding
    model only once regardless of how many sources are configured.
    """
    from indexing.gitlab_repo_fetcher import fetch_repo_documents
    from indexing.gitlab_wiki_fetcher import fetch_wiki_documents

    if config is None:
        config = IndexingConfig.from_env()
    pat = token or config.gitlab_pat

    if not pat:
        raise ValueError(
            "GITLAB_PAT is niet ingesteld. Zonder token geeft GitLab 404 op "
            "private projecten. Stel GITLAB_PAT in via .env en herstart de service."
        )

    all_documents = []

    for url in config.gitlab_wiki_urls:
        log_info(f"Ophalen wiki: {url}")
        try:
            all_documents.extend(fetch_wiki_documents(url, token=pat))
        except ConnectionError:
            log_warn(
                f"Kan geen verbinding maken met GitLab ({url}). "
                "Controleer of de VPN is ingeschakeld en het URL correct is. "
                "Deze bron wordt overgeslagen."
            )

    for url in config.gitlab_repo_urls:
        log_info(f"Ophalen repo: {url}")
        try:
            all_documents.extend(fetch_repo_documents(url, token=pat))
        except ConnectionError:
            log_warn(
                f"Kan geen verbinding maken met GitLab ({url}). "
                "Controleer of de VPN is ingeschakeld en het URL correct is. "
                "Deze bron wordt overgeslagen."
            )

    log_info(f"Totaal opgehaalde documenten: {len(all_documents)}")
    _run_pipeline(all_documents, config, full_reindex=full_reindex)


def build_abbreviations_from_docstore(config: Optional[IndexingConfig] = None) -> None:
    """Backfill abbreviations.json from the existing docstore without re-indexing.

    Useful when documents are already indexed but abbreviations.json is missing
    (e.g. after upgrading from a version that didn't have this feature).
    """
    if config is None:
        config = IndexingConfig.from_env()

    docstore_path = Path(config.docstore_path)
    abbreviations_path = Path(config.abbreviations_path)

    if not docstore_path.exists():
        log_warn(f"Docstore niet gevonden: {docstore_path}")
        return

    raw = json.loads(docstore_path.read_text(encoding="utf-8"))
    nodes = raw.get("docstore/data", {})
    log_info(f"Afkortingen opbouwen uit {len(nodes)} nodes in docstore ...")

    # Track which source_urls we've already processed to avoid duplicate work
    seen_sources: set = set()
    total_entries = 0

    for node_data in nodes.values():
        data = node_data.get("__data__", {})
        text = data.get("text", "")
        metadata = data.get("metadata", {})
        source_url = metadata.get("source_url", metadata.get("file_path", ""))

        if not text or not source_url or source_url in seen_sources:
            continue
        seen_sources.add(source_url)

        entries = _extract_abbreviations(text, metadata)
        if entries:
            _update_abbreviations_file(entries, [source_url], abbreviations_path)
            total_entries += len(entries)
            log_info(f"  {len(entries)} afkorting(en) uit {metadata.get('file_name', source_url)}")

    log_success(f"Klaar. {total_entries} afkortingen opgeslagen in {abbreviations_path}")


def run_indexing_pipeline(
    data_dir: Optional[str] = None,
    full_reindex: bool = False,
    build_abbreviations: bool = False,
) -> None:
    """Entry point used by generating.indexing_runner to trigger a full index run.

    data_dir is accepted for API compatibility but ignored — all paths are
    resolved from env vars via IndexingConfig.from_env().
    """
    if build_abbreviations:
        build_abbreviations_from_docstore()
    else:
        run_all_sources_pipeline(full_reindex=full_reindex)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Index GitLab wiki pages and repository files into Qdrant. "
            "Sources are configured via GITLAB_WIKI_URLS and GITLAB_REPO_URLS in .env."
        ),
    )
    parser.add_argument(
        "--gitlab-token",
        metavar="TOKEN",
        default=None,
        help="GitLab Personal Access Token. Overrides GITLAB_PAT environment variable.",
    )
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        default=False,
        help=(
            "Drop the Qdrant collections and docstore, then re-index everything "
            "from scratch. Changes to PARENT_CHUNK_SIZE, CHILD_CHUNK_SIZE, "
            "PARENT_CHUNK_OVERLAP, or EMBED_MODEL are detected automatically "
            "via the index_meta version stamp; this flag forces a rebuild on demand."
        ),
    )
    parser.add_argument(
        "--build-abbreviations",
        action="store_true",
        default=False,
        help=(
            "Rebuild abbreviations.json from the existing docstore without re-indexing. "
            "Use this once after upgrading to add abbreviation support to an existing index."
        ),
    )

    args = parser.parse_args()

    config = IndexingConfig.from_env()

    if args.build_abbreviations:
        build_abbreviations_from_docstore(config=config)
        raise SystemExit(0)

    token = args.gitlab_token or config.gitlab_pat or None

    if not config.gitlab_wiki_urls and not config.gitlab_repo_urls:
        parser.print_help()
        raise SystemExit(
            "\nFout: stel GITLAB_WIKI_URLS en/of GITLAB_REPO_URLS in de omgeving in."
        )

    if not token:
        raise SystemExit(
            "Fout: GITLAB_PAT is niet ingesteld. "
            "Voeg het toe aan .env of geef --gitlab-token <token> mee."
        )

    run_all_sources_pipeline(token=token, config=config, full_reindex=args.full_reindex)
