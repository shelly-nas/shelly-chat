"""Abbreviation definitions: extracted from documents, used to expand questions.

Extraction runs when the indexer stores a document; expansion runs before the
browser embeds a question. Both are plain text processing - no model involved -
which is why they live on the NAS rather than next to Ollama.
"""

import re

# ── Extraction ───────────────────────────────────────────────────────────────

# Pattern A: ABBREV (Full Term) - e.g. "VI (Versleutelde Identiteit)"
_ABBREV_THEN_TERM = re.compile(r"\b([A-Z][A-Za-z0-9]{1,7})\s*\(([^)]{3,80})\)")
# Pattern B: Full Term (ABBREV) - e.g. "Versleutelde Identiteit (VI)"
# Captures up to 4 words starting at a capital-letter boundary before the parenthesis.
_TERM_THEN_ABBREV = re.compile(
    r"(?<![A-Za-z])"
    r"([A-Z][a-zA-Z]*(?:\s+[a-zA-Z]+){0,3})"
    r"\s*\(([A-Z][A-Za-z0-9]{1,7})\)"
)
# Guard: abbreviation must contain ≥2 uppercase letters
_MIN_UPPER = re.compile(r"[A-Z].*[A-Z]")

# Leading words that are never part of the term an abbreviation stands for.
_STOP_WORDS = frozenset(
    """
    de het een en of van in op aan met voor door bij naar over om uit als dat die
    dit deze is zijn wordt worden ook niet tot onder tussen
    the a an and or of in on at to for by with from as is are be this that these
    """.split()
)


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


def is_valid_abbreviation(abbrev: str, term: str) -> bool:
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

        # Priority 1: boundary match - skip only words whose letter is not needed
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


def extract_abbreviations(text: str, source_url: str, file_name: str) -> list[dict]:
    """Extract validated inline abbreviation definitions from document text.

    Finds both 'ABBREV (Full Term)' and 'Full Term (ABBREV)' patterns, then
    validates each pair using initialism/subsequence rules before keeping it.
    """
    entries: list[dict] = []
    seen: set = set()

    def _add(abbrev: str, term: str, match_start: int, match_end: int) -> None:
        if not _MIN_UPPER.search(abbrev):
            return
        if not is_valid_abbreviation(abbrev, term):
            return
        term = _strip_term(term)  # store clean term without leading stop words
        if not term:
            return
        key = (abbrev, term)
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


# ── Expansion ────────────────────────────────────────────────────────────────

# Abbreviation-shaped tokens in a question (the lookup itself is
# case-insensitive). Accepts VI, vi, BSN, DigiD; rejects single letters and
# long words through the length bounds.
_QUERY_TOKEN = re.compile(r"\b[A-Za-z]{2,8}\b")


def query_tokens(query: str) -> list[str]:
    return list(dict.fromkeys(_QUERY_TOKEN.findall(query)))


def expand_query(query: str, entries_by_abbrev: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    """Expand known abbreviations: 'VI' becomes 'VI (Versleutelde Identiteit)'.

    entries_by_abbrev maps upper(abbrev) to every stored definition of it.
    Only the first occurrence of each token is expanded, with the first
    definition; all definitions are returned so the UI can show each source.
    """
    enriched = query
    applied: list[dict] = []
    for token in query_tokens(query):
        matches = entries_by_abbrev.get(token.upper(), [])
        if not matches:
            continue
        canonical = matches[0].get("abbrev", token)
        term = matches[0].get("term", "")
        if not term:
            continue
        enriched = re.sub(
            rf"\b{re.escape(token)}\b", f"{canonical} ({term})", enriched, count=1
        )
        applied.extend(matches)
    return enriched, applied
