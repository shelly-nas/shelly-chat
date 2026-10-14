"""Turning a file from the documents folder into hierarchical chunks.

Both ways of indexing - the Index screen in the app and the CLI in host/ -
ask the NAS to prepare each document: read it from the documents folder,
extract the text, hash it and split it. Only the embedding happens on the
user's machine, where Ollama runs.

No model is involved: HierarchicalNodeParser is a token-counting text
splitter, with its tokenizer shipped inside llama-index-core.
"""

import hashlib
import re
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, SentenceSplitter, get_leaf_nodes
from llama_index.core.schema import MetadataMode


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

        # Word headings become Markdown headings, so chunks know their section.
        return "\n".join(_docx_line(p) for p in docx.Document(str(path)).paragraphs)
    raise ValueError(f"Bestandstype {ext or '(geen)'} wordt niet ondersteund.")


def _docx_line(paragraph) -> str:
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    # English and Dutch Word: "Heading 2" / "Kop 2", "Title" / "Titel".
    match = re.match(r"(?:Heading|Kop)\s*(\d)", style)
    if match and paragraph.text.strip():
        return f"{'#' * min(int(match.group(1)), 6)} {paragraph.text.strip()}"
    if style in ("Title", "Titel") and paragraph.text.strip():
        return f"# {paragraph.text.strip()}"
    return paragraph.text


# Bump when split() changes what it stores or embeds: every document then
# counts as changed and is split and embedded again on the next run, without
# emptying the indexes first.
SPLIT_VERSION = "2"


def content_hash(text: str) -> str:
    return hashlib.sha256(f"split-v{SPLIT_VERSION}\n{text}".encode("utf-8")).hexdigest()


_HEADING = re.compile(r"^(?:(#{1,6})|(={1,6}))[ \t]+(.+?)[ \t#=]*$", re.MULTILINE)


def headings(text: str) -> list[tuple[int, int, str]]:
    """(position, level, title) of every Markdown (#) or AsciiDoc (=) heading."""
    return [(m.start(), len(m.group(1) or m.group(2)), m.group(3).strip()) for m in _HEADING.finditer(text)]


def section_at(heads: list[tuple[int, int, str]], position: int) -> str:
    """The heading path in force at `position`: "Contract › Artikel 4 › Opzegging"."""
    path: list[tuple[int, str]] = []
    for start, level, title in heads:
        if start > position:
            break
        path = [p for p in path if p[0] < level] + [(level, title)]
    return " › ".join(title for _, title in path)


def split(text: str, metadata: dict, hash_: str, chunks: dict) -> list[dict]:
    """Hierarchical chunks; leaves carry the text the embedding is made of."""
    doc = Document(text=text, metadata={**metadata, "content_hash": hash_})
    # The hash identifies the document version; it must not end up in what
    # gets embedded or shown to the model.
    # source_url is an app link (/api/files/...), not something to search on.
    for key in ("content_hash", "source_url"):
        doc.excluded_embed_metadata_keys.append(key)
        doc.excluded_llm_metadata_keys.append(key)

    # chunks: parent_chunk_size, child_chunk_size, parent_chunk_overlap (the
    # shared settings). The overlap applies between parents; leaves inside a
    # parent keep LlamaIndex's small default overlap.
    parser = HierarchicalNodeParser.from_defaults(
        node_parser_ids=["parent", "child"],
        node_parser_map={
            "parent": SentenceSplitter(
                chunk_size=chunks["parent_chunk_size"], chunk_overlap=chunks["parent_chunk_overlap"]
            ),
            "child": SentenceSplitter(
                chunk_size=chunks["child_chunk_size"], chunk_overlap=min(20, chunks["child_chunk_size"] // 4)
            ),
        },
    )
    all_nodes = parser.get_nodes_from_documents([doc])
    leaf_ids = {n.node_id for n in get_leaf_nodes(all_nodes)}

    # The heading path of each chunk goes into its metadata, and so into what
    # is embedded: a paragraph about "opzegging" under "Contract X › Artikel 4"
    # is found by a question about contract X. Added after splitting, so it
    # does not change where the chunks are cut.
    heads = headings(text)
    if heads:
        found: dict[str, int] = {}
        for node in all_nodes:  # parents come before their children
            parent = node.parent_node
            start = found.get(parent.node_id, 0) if parent else 0
            pos = text.find(node.get_content()[:200], start)
            found[node.node_id] = pos if pos >= 0 else start
            section = section_at(heads, found[node.node_id])
            if section:
                node.metadata["section_context"] = section

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
