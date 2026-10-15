"""Index the named indexes of shelly-chat from the command line.

The same run as the Index screens in the app (client/src/lib/indexer.ts), for
when a terminal or a scheduled job is handier than a browser tab. It runs on a
machine with Ollama; the documents themselves stay on the NAS:

1. The embedding model and the chunk configuration (Settings in the app) are shared by
   all indexes. A different model, dimension or chunk configuration than the
   store was built with empties it: every index is then indexed again.
2. Per index, the NAS lists the documents in its sources minus its ignore
   patterns (GET /api/indexes/{id}/files), then reads, hashes and splits each
   one (POST /api/index/prepare). A document already embedded - perhaps for
   another index - just joins this one; for the others the leaf chunks are
   embedded with the local Ollama and stored (PUT /api/index/documents).
3. Documents that left the index are dropped from it (POST .../prune) - only
   when every source could be read, so a missing folder never empties an index.

    python -m indexing.indexer                    # every index
    python -m indexing.indexer --index "Mijn BV"  # one index
    python -m indexing.indexer --full-reindex     # empty the store, index everything
    python -m indexing.indexer --build-abbreviations
"""

import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

from indexing.console import log_error, log_info, log_success, log_warn
from indexing.nas_client import NasClient, NasError
from indexing.ollama import OllamaEmbedder, describe_image, unload_model

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")


@dataclass
class IndexingConfig:
    server_url: str = "http://localhost:3000"
    index_token: str = ""
    # Set from the NAS at the start of a run (Settings → Indexeren in the app).
    embed_model: str = "qwen3-embedding:latest"
    ollama_base_url: str = "http://localhost:11434"
    embed_batch_size: int = 16

    @classmethod
    def from_env(cls) -> "IndexingConfig":
        return cls(
            server_url=os.getenv("SHELLY_CHAT_URL", "http://localhost:3000"),
            index_token=os.getenv("INDEX_TOKEN", ""),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            embed_batch_size=int(os.getenv("EMBED_BATCH_SIZE", "16")),
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


def describe(prepared: dict, index_id: int, nas: NasClient, embedder: OllamaEmbedder, vision: dict) -> dict:
    """Have the vision model describe the document's images, then prepare it again with them."""
    descriptions = {}
    for visual in prepared.get("visuals", []):
        try:
            image = nas.visual(prepared["file_path"], visual["id"])
            text = describe_image(embedder.base_url, vision["model"], vision["prompt"], image)
            if text:
                descriptions[visual["id"]] = text
        except (NasError, RuntimeError, requests.RequestException) as exc:
            log_warn(f"  {prepared['file_path']}: {visual['label']} beschrijven mislukt — {exc}")
    log_info(f"  {prepared['file_path']}: {len(descriptions)} afbeelding(en) beschreven met {vision['model']}")
    return nas.prepare_document(prepared["file_path"], index_id, descriptions)


def store_document(
    file_path: str, index_id: int, nas: NasClient, embedder: OllamaEmbedder, vision: Optional[dict] = None
) -> Optional[dict]:
    """Prepare, embed and store one document for an index. Returns the outcome, or None if unchanged."""
    prepared = nas.prepare_document(file_path, index_id)
    if prepared["status"] == "describe":
        prepared = describe(prepared, index_id, nas, embedder, vision or {})
    if prepared["status"] not in ("new", "changed"):
        return None

    document = prepared["document"]
    leaves = [n for n in document["nodes"] if n["is_leaf"]]
    vectors = embedder.embed([n["embed_text"] for n in leaves])
    by_id = {n["id"]: v for n, v in zip(leaves, vectors)}
    document["nodes"] = [
        {**{k: v for k, v in n.items() if k != "embed_text"}, "embedding": by_id.get(n["id"])}
        for n in document["nodes"]
    ]
    document["index_id"] = index_id
    stored = nas.put_document(document)
    return {"status": prepared["status"], **stored}


def index_one(
    index: dict, nas: NasClient, embedder: OllamaEmbedder, counts: Dict[str, int], vision: Optional[dict] = None
) -> None:
    name = index["name"]
    listing = nas.index_files(index["id"])
    for source in listing["missing"]:
        log_error(f"{name}: bron '{source or '.'}' bestaat niet (meer) in de documentenmap; overgeslagen.")
    files = listing["files"]
    log_info(f"{name}: {len(files)} documenten.")

    for i, path in enumerate(files, 1):
        try:
            outcome = store_document(path, index["id"], nas, embedder, vision)
        except (NasError, RuntimeError) as exc:
            counts["failed"] += 1
            log_error(f"  [{i}/{len(files)}] {path}: {exc}")
            continue
        if outcome is None:
            counts["unchanged"] += 1
            continue
        counts[outcome["status"]] += 1
        extra = f", {outcome['abbreviations']} afkorting(en)" if outcome["abbreviations"] else ""
        label = "nieuw" if outcome["status"] == "new" else "gewijzigd"
        log_info(f"  [{i}/{len(files)}] {path}: {label}, {outcome['chunks']} chunks{extra}")

    if listing["missing"]:
        log_warn(f"{name}: niets uit de index gehaald, want niet elke bron kon worden gelezen.")
        return
    pruned = nas.prune_index(index["id"], files)
    counts["deleted"] += pruned["removed"]
    if pruned["removed"]:
        log_info(f"{name}: {pruned['removed']} document(en) uit de index gehaald die er niet meer in horen.")


def run_pipeline(config: IndexingConfig, full_reindex: bool = False, only: Optional[str] = None) -> Dict[str, int]:
    counts = {"new": 0, "changed": 0, "unchanged": 0, "deleted": 0, "failed": 0}
    nas = config.nas()
    settings = nas.settings()
    config.embed_model = settings["embed_model"]
    embedder = config.embedder()
    # Describing images and drawings (Instellingen → Indexeren); model "" is off.
    vision = settings.get("vision") or {"model": "", "prompt": ""}

    indexes: List[dict] = nas.indexes()
    if only is not None:
        indexes = [i for i in indexes if i["name"].lower() == only.lower()]
        if not indexes:
            raise SystemExit(f"Er is geen index '{only}'. Indexen maak je op het scherm Indexen in de app.")
    if not indexes:
        raise SystemExit("Er zijn nog geen indexen. Maak ze op het scherm Indexen in de app.")

    # One run at a time, also against the app (see server/app/runlock.py).
    run_id = uuid.uuid4().hex
    label = "CLI: " + ", ".join(i["name"] for i in indexes)
    try:
        nas.lease_run(run_id, label)
    except NasError as exc:
        raise SystemExit(str(exc)) from None
    stop = threading.Event()

    def keep_lease() -> None:
        while not stop.wait(30):
            try:
                nas.lease_run(run_id, label)
            except NasError as exc:
                log_warn(f"Slot op de NAS verlengen mislukt — {exc}")

    threading.Thread(target=keep_lease, daemon=True).start()
    try:
        # 1. Model, dimension and whether to start over (shared by all indexes)
        meta = settings["meta"]
        if meta and meta["embed_model"] == config.embed_model:
            dimensions = meta["embed_dimensions"]
        else:
            log_info(f"Embeddingmodel {config.embed_model} laden om de dimensie te bepalen ...")
            dimensions = embedder.dimensions()
        reason = reset_reason(meta, settings["chunk_config"], config.embed_model, dimensions)
        if reason:
            log_warn(f"Alle indexen worden opnieuw opgebouwd: {reason}.")
        nas.put_meta({"embed_model": config.embed_model, "embed_dimensions": dimensions}, reset=full_reindex or reason is not None)

        # 2-3. Each index
        try:
            for index in indexes:
                index_one(index, nas, embedder, counts, vision)
        finally:
            try:
                embedder.unload()
                if vision["model"]:
                    unload_model(embedder.base_url, vision["model"])
            except Exception as exc:
                log_warn(f"Model ontladen mislukt — {exc}")
    finally:
        stop.set()
        try:
            nas.end_run(run_id)
        except NasError:
            pass

    log_success(
        f"Klaar: {counts['new']} nieuw, {counts['changed']} gewijzigd, {counts['unchanged']} ongewijzigd, "
        f"{counts['deleted']} uit een index gehaald, {counts['failed']} mislukt."
    )
    return counts


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Werk de indexen van shelly-chat bij. Indexen, bronnen en ignore-patronen beheer je op "
            "het scherm Indexen in de app; de NAS staat in SHELLY_CHAT_URL (host/.env)."
        ),
    )
    parser.add_argument("--index", metavar="NAAM", default=None, help="Alleen deze index; standaard alle indexen.")
    parser.add_argument("--full-reindex", action="store_true", help="Leeg alle indexen en indexeer alles opnieuw.")
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
    run_pipeline(config, full_reindex=args.full_reindex, only=args.index)


if __name__ == "__main__":
    main()
