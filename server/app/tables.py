"""Tables in documents: written as Markdown tables, and kept readable in chunks.

Every reader (PDF, Word, Excel, CSV) turns a table into a Markdown table with
its header row, so a cell keeps the name of its column. Before splitting, a
table too large for one small chunk is cut into pieces of whole rows that
each repeat the header: a chunk with rows "2024-0193 | 1.200 | 1 maart"
still says these are "Factuur | Bedrag | Vervaldatum", for the search and
for the model.
"""

import re

# LlamaIndex's SentenceSplitter keeps a paragraph whole when it fits in a
# chunk, and splits between paragraphs first; this is its paragraph separator.
PARAGRAPH = "\n\n\n"

# A piece may fill this share of a small chunk: the rest is room for the
# metadata (file name, section) that the splitter counts as well.
FILL = 0.75


def _tokens(text: str) -> int:
    """Tokens as the splitter counts them (LlamaIndex's default tokenizer)."""
    from llama_index.core.utils import get_tokenizer

    return len(get_tokenizer()(text))


def _cell(value) -> str:
    if value is None:
        return ""
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return " ".join(text.split()).replace("|", "\\|")


def markdown_table(rows: list[list]) -> str:
    """A Markdown table from rows of cells; the first non-empty row is the header."""
    cleaned = [[_cell(c) for c in row] for row in rows if row is not None]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]
    # Columns that are empty everywhere (layout artefacts) carry no meaning.
    keep = [i for i in range(width) if any(row[i] for row in cleaned)]
    cleaned = [[row[i] for i in keep] for row in cleaned]
    header, body = cleaned[0], cleaned[1:]
    header = [h or f"Kolom {i + 1}" for i, h in enumerate(header)]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _is_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def keep_tables_whole(text: str, child_chunk_tokens: int) -> str:
    """Cut every Markdown table into pieces that fit a small chunk, each with the header.

    The pieces become paragraphs of their own, so the splitter keeps each one
    whole. Text outside tables is left as it is.
    """
    budget = max(50, int(child_chunk_tokens * FILL))
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and _is_row(lines[i]) and _SEPARATOR.match(lines[i + 1].strip()):
            header, separator = lines[i], lines[i + 1]
            j = i + 2
            rows = []
            while j < len(lines) and _is_row(lines[j]):
                rows.append(lines[j])
                j += 1
            pieces, piece = [], []
            head = _tokens(header + "\n" + separator)
            size = head
            for row in rows:
                cost = _tokens(row) + 1
                if piece and size + cost > budget:
                    pieces.append(piece)
                    piece, size = [], head
                piece.append(row)
                size += cost
            pieces.append(piece)
            tables = ["\n".join([header, separator, *piece]) for piece in pieces]
            out.append(PARAGRAPH + PARAGRAPH.join(tables) + PARAGRAPH)
            i = j
        else:
            out.append(lines[i])
            i += 1
    # Join, then collapse the extra blank lines the paragraph breaks added.
    return re.sub(r"\n{4,}", PARAGRAPH, "\n".join(out)).strip("\n")
