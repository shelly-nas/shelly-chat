"""Query expansion via abbreviation dictionary lookup.

Detects domain-specific abbreviations in a user query and enriches them
by looking up their definitions in abbreviations.json (built at index time).
This is fast and deterministic — no embedding model or LLM call needed.

Flow:
  1. Detect tokens with 2+ uppercase letters on word boundaries
  2. Look up each token in the abbreviations dictionary
  3. Replace the first occurrence in the query: 'VI' → 'VI (Versleutelde Identiteit)'
  4. Return the enriched query plus all matching entries for UI display
  5. On any error the original query is returned unchanged
"""

import json
import logging
import os
import re
from typing import Optional

from llama_index.core.llms import ChatMessage, MessageRole

logger = logging.getLogger(__name__)

# Matches abbreviation-shaped tokens in the user's query (case-insensitive dict
# lookup handles the actual matching). Accepts VI, vi, BSN, DigiD; rejects
# single letters and long common words via length bounds (2–8 chars).
_ABBREV_PATTERN = re.compile(r"\b[A-Za-z]{2,8}\b")

# ── Dict-based expansion (fast path) ─────────────────────────────────────────

_abbrev_cache: list = []
_abbrev_cache_mtime: float = 0.0


def load_abbreviations(path: str) -> list:
    """Load abbreviations.json with mtime-based cache invalidation."""
    global _abbrev_cache, _abbrev_cache_mtime

    try:
        mtime = os.path.getmtime(path)
        if mtime == _abbrev_cache_mtime and _abbrev_cache:
            return _abbrev_cache

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        _abbrev_cache = data if isinstance(data, list) else []
        _abbrev_cache_mtime = mtime
        logger.info("Abbreviations loaded: %d entries from %s", len(_abbrev_cache), path)
        return _abbrev_cache

    except FileNotFoundError:
        logger.info("Abbreviations file not found at %s — expansion skipped", path)
        return []
    except Exception as exc:
        logger.warning("Failed to load abbreviations from %s: %s", path, exc)
        return []


def expand_query_from_dict(query: str, abbreviations_path: str) -> tuple:
    """Expand abbreviations in query using the pre-built dictionary.

    Returns (enriched_query, expansions_applied) where expansions_applied is
    a list of dicts: {abbrev, term, source_url, file_name, snippet}.
    Multiple entries for the same abbreviation (different sources) are all
    included in expansions_applied so the UI can show every source.
    """
    abbreviations = load_abbreviations(abbreviations_path)
    if not abbreviations:
        return query, []

    detected = list(dict.fromkeys(_ABBREV_PATTERN.findall(query)))
    if not detected:
        return query, []

    logger.info("Query expansion (dict): detected abbreviations %s in %r", detected, query)

    # Build case-insensitive index: upper(abbrev) → list of entries
    index: dict = {}
    for entry in abbreviations:
        abbrev = entry.get("abbrev", "")
        if abbrev:
            index.setdefault(abbrev.upper(), []).append(entry)

    enriched = query
    applied: list = []

    for token in detected:
        matches = index.get(token.upper(), [])
        if not matches:
            continue

        # Use the canonical abbreviation spelling from the dict entry
        canonical = matches[0].get("abbrev", token)
        term = matches[0].get("term", "")
        if not term:
            continue

        # Replace the token as written in the query with "TOKEN (term)"
        enriched = re.sub(
            rf"\b{re.escape(token)}\b",
            f"{canonical} ({term})",
            enriched,
            count=1,
        )
        applied.extend(matches)
        logger.info("  Expanded '%s' → '%s (%s)' (%d source(s))", token, canonical, term, len(matches))

    if enriched != query:
        logger.info("Query expansion result: %r → %r", query, enriched)
    else:
        logger.info("Query expansion result: no matches in dictionary")

    return enriched, applied


# ── Legacy RAG-based expansion (kept for reference, no longer called) ─────────

_SYSTEM_PROMPT = (
    "Jij extraheert de volledige term van een afkorting op basis van documentatie. "
    "Geef ALLEEN de volledige term terug, zonder uitleg of zin. "
    "Als de afkorting niet in de documentatie staat, antwoord dan met 'onbekend'. "
    "/no_think"
)

_USER_TEMPLATE = (
    "Wat is de volledige term voor de afkorting '{abbrev}' op basis van de volgende documentatie?\n\n"
    "DOCUMENTATIE:\n{context}\n\n"
    "Volledige term voor {abbrev}:"
)


def retrieve_expansion_contexts(
    query: str,
    index,
    storage_context,
    expansion_top_k: int,
) -> dict:
    """Legacy Phase 1: retrieve context text per detected abbreviation. No longer called."""
    abbreviations = list(dict.fromkeys(_ABBREV_PATTERN.findall(query)))
    if not abbreviations:
        return {}

    logger.info("Query expansion: detected abbreviations %s in %r", abbreviations, query)

    retriever = index.as_retriever(similarity_top_k=expansion_top_k)

    contexts: dict = {}
    for abbrev in abbreviations:
        try:
            nodes = retriever.retrieve(f"Wat betekent {abbrev}?")
        except Exception as exc:
            logger.warning("  Expansion retrieval failed for '%s': %s", abbrev, exc)
            continue

        if not nodes:
            logger.info("  No nodes found for '%s'", abbrev)
            continue

        context = "\n\n".join(n.get_content() for n in nodes)
        contexts[abbrev] = context
        logger.info("  Retrieved %d node(s) for '%s'", len(nodes), abbrev)

    return contexts


def apply_expansions(
    query: str,
    contexts: dict,
    llm,
) -> str:
    """Legacy Phase 2: ask the LLM for definitions and enrich the query. No longer called."""
    if not contexts:
        return query

    enriched = query
    for abbrev, context in contexts.items():
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=_SYSTEM_PROMPT),
            ChatMessage(
                role=MessageRole.USER,
                content=_USER_TEMPLATE.format(abbrev=abbrev, context=context),
            ),
        ]

        try:
            response = llm.chat(messages)
            term = (response.message.content or "").strip()
        except Exception as exc:
            logger.warning("  LLM call failed during expansion for '%s': %s", abbrev, exc)
            continue

        logger.info("  LLM raw response for '%s': %r", abbrev, term)

        term = re.sub(r"<think>.*?</think>", "", term, flags=re.DOTALL).strip()

        if not term or "onbekend" in term.lower() or len(term) > 120:
            logger.info("  Rejected definition for '%s': %r", abbrev, term)
            continue

        enriched = re.sub(
            rf"\b{re.escape(abbrev)}\b",
            f"{abbrev} ({term})",
            enriched,
            count=1,
        )
        logger.info("  Expanded '%s' → '%s (%s)'", abbrev, abbrev, term)

    if enriched != query:
        logger.info("Query expansion result: %r → %r", query, enriched)
    else:
        logger.info("Query expansion result: no changes")

    return enriched
