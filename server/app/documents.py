"""Turning a file from the documents folder into hierarchical chunks.

Both ways of indexing - the Index screen in the app and the CLI in host/ -
ask the NAS to prepare each document: read it from the documents folder,
extract the text, hash it and split it. Only the embedding happens on the
user's machine, where Ollama runs.

No model is involved: HierarchicalNodeParser is a token-counting text
splitter, with its tokenizer shipped inside llama-index-core.
"""

import hashlib
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core.schema import MetadataMode

from app import config


def extract_text(path: Path) -> str:
    """The plain text of a Markdown, text, PDF or DOCX file."""
    ext = path.suffix.lower()
    if ext in (".md", ".adoc", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        from pdfminer.high_level import extract_text as pdf_text

        return pdf_text(str(path)) or ""
    if ext in (".docx", ".doc"):
        import docx

        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    raise ValueError(f"Bestandstype {ext or '(geen)'} wordt niet ondersteund.")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_config() -> dict:
    return {
        "parent_chunk_size": config.PARENT_CHUNK_SIZE,
        "child_chunk_size": config.CHILD_CHUNK_SIZE,
        "parent_chunk_overlap": config.PARENT_CHUNK_OVERLAP,
    }


def split(text: str, metadata: dict, hash_: str) -> list[dict]:
    """Hierarchical chunks; leaves carry the text the embedding is made of."""
    doc = Document(text=text, metadata={**metadata, "content_hash": hash_})
    # The hash identifies the document version; it must not end up in what
    # gets embedded or shown to the model.
    # source_url is an app link (/api/files/...), not something to search on.
    for key in ("content_hash", "source_url"):
        doc.excluded_embed_metadata_keys.append(key)
        doc.excluded_llm_metadata_keys.append(key)

    parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=[config.PARENT_CHUNK_SIZE, config.CHILD_CHUNK_SIZE]
    )
    all_nodes = parser.get_nodes_from_documents([doc])
    leaf_ids = {n.node_id for n in get_leaf_nodes(all_nodes)}

    nodes = []
    for position, node in enumerate(all_nodes):
        parent = node.parent_node
        is_leaf = node.node_id in leaf_ids
        nodes.append({
            "id": node.node_id,
            "parent_id": parent.node_id if parent else None,
            "is_leaf": is_leaf,
            "position": position,
            "content": node.get_content(),
            "metadata": node.metadata,
            # What LlamaIndex would embed: the text plus the metadata that is
            # not excluded from embedding (title, file name, URL).
            "embed_text": node.get_content(metadata_mode=MetadataMode.EMBED) if is_leaf else None,
        })
    return nodes
