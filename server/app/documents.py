"""Turning a file from the documents folder into hierarchical chunks.

Both ways of indexing - the Index screen in the app and the CLI in host/ -
ask the NAS to prepare each document: read it from the documents folder,
extract the text, hash it and split it. Only the embedding happens on the
user's machine, where Ollama runs.

No model is involved: HierarchicalNodeParser is a token-counting text
splitter, with its tokenizer shipped inside llama-index-core.

Tables are read as tables (app/tables.py): PDF tables through pdfplumber's
table detection, Word tables in document order, Excel sheets and CSV files.
"""

import csv
import hashlib
import io
import logging
import re
from pathlib import Path

from app import tables

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, SentenceSplitter, get_leaf_nodes
from llama_index.core.schema import MetadataMode


logger = logging.getLogger(__name__)


def extract_text(path: Path) -> str:
    """The text of a document, with headings as Markdown headings and tables as Markdown tables."""
    ext = path.suffix.lower()
    if ext in (".md", ".adoc", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        return _pdf_text(path)
    if ext in (".docx", ".doc"):
        return _docx_text(path)
    if ext == ".xlsx":
        return _xlsx_text(path)
    if ext == ".csv":
        return _csv_text(path)
    raise ValueError(f"Bestandstype {ext or '(geen)'} wordt niet ondersteund.")


def _pdf_text(path: Path) -> str:
    """Text and tables of a PDF in reading order, page by page.

    pdfplumber finds ruled tables; each becomes a Markdown table, and the text
    above, between and below them is read as text. Falls back to plain
    pdfminer text if pdfplumber cannot read the file.
    """
    try:
        import pdfplumber

        parts: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                x0, top, x1, bottom = page.bbox

                def text_between(upper: float, lower: float) -> str:
                    if lower - upper < 1:
                        return ""
                    return page.crop((x0, upper, x1, lower)).extract_text() or ""

                cursor = top
                for table in sorted(page.find_tables(), key=lambda t: t.bbox[1]):
                    _, t_top, _, t_bottom = table.bbox
                    t_top, t_bottom = max(t_top, cursor), min(t_bottom, bottom)
                    if t_bottom <= t_top:
                        continue
                    parts.append(text_between(cursor, t_top))
                    rows = table.extract()
                    markdown = tables.markdown_table(rows) if len(rows) >= 2 else ""
                    # A "table" of one row is usually a framed line of text.
                    parts.append(markdown or text_between(t_top, t_bottom))
                    cursor = t_bottom
                parts.append(text_between(cursor, bottom))
        return "\n\n".join(p.strip() for p in parts if p.strip())
    except Exception as exc:  # pdfplumber is stricter than pdfminer on broken files
        logger.warning("pdfplumber kon %s niet lezen (%s); platte tekst via pdfminer", path, exc)
        from pdfminer.high_level import extract_text as pdf_text

        return pdf_text(str(path)) or ""


def _docx_text(path: Path) -> str:
    """Paragraphs and tables in document order; headings and tables as Markdown."""
    import docx
    from docx.table import Table

    lines = []
    for block in docx.Document(str(path)).iter_inner_content():
        if isinstance(block, Table):
            rows = [[cell.text for cell in row.cells] for row in block.rows]
            lines += ["", tables.markdown_table(rows), ""]
        else:
            lines.append(_docx_line(block))
    return "\n".join(lines)


def _xlsx_text(path: Path) -> str:
    """Every sheet as a heading with its cells as a Markdown table (values, not formulas)."""
    import openpyxl

    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        parts = []
        for sheet in workbook.worksheets:
            table = tables.markdown_table([list(row) for row in sheet.iter_rows(values_only=True)])
            if table:
                parts.append(f"# {sheet.title}\n\n{table}")
        return "\n\n".join(parts)
    finally:
        workbook.close()


def _csv_text(path: Path) -> str:
    """A CSV file as a Markdown table; the delimiter (, ; or tab) is detected."""
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw[:20_000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return tables.markdown_table(list(csv.reader(io.StringIO(raw), dialect)))


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
SPLIT_VERSION = "3"


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
    # Large tables become pieces that fit a small chunk, each with its header.
    text = tables.keep_tables_whole(text, chunks["child_chunk_size"])
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
