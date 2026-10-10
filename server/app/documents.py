"""Turning a fetched document into hierarchical chunks.

Both ways of indexing - the Index screen in the app and the CLI in host/ -
fetch documents from GitLab on the user's machine and send them here: plain
text for Markdown, base64 bytes for PDF and DOCX. The NAS extracts the text,
hashes it and splits it, so every document gets the same chunks whichever way
it was indexed. Only the embedding happens back on the user's machine.

No model is involved: HierarchicalNodeParser is a token-counting text
splitter, with its tokenizer shipped inside llama-index-core.
"""

import base64
import hashlib
import io

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core.schema import MetadataMode

from app import config

TEXT_EXTENSIONS = {".md", ".adoc", ".txt"}
BINARY_EXTENSIONS = {".pdf", ".docx", ".doc"}


def extension(file_name: str) -> str:
    name = file_name.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def extract_text(file_name: str, text: str | None, data_base64: str | None) -> str:
    """The plain text of a document, from text or from base64 file bytes."""
    if text is not None:
        return text
    if data_base64 is None:
        raise ValueError("Stuur text of data_base64 mee.")
    raw = base64.b64decode(data_base64)
    ext = extension(file_name)
    if ext in TEXT_EXTENSIONS:
        return raw.decode("utf-8", errors="replace")
    if ext == ".pdf":
        from pdfminer.high_level import extract_text as pdf_text

        return pdf_text(io.BytesIO(raw)) or ""
    if ext in (".docx", ".doc"):
        import docx

        return "\n".join(p.text for p in docx.Document(io.BytesIO(raw)).paragraphs)
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
    doc.excluded_embed_metadata_keys.append("content_hash")
    doc.excluded_llm_metadata_keys.append("content_hash")

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
