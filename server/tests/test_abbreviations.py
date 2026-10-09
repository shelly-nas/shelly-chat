from app.abbreviations import expand_query, extract_abbreviations, is_valid_abbreviation


def test_extracts_both_notations():
    text = (
        "Een VI (Versleutelde Identiteit) wordt gebruikt in de keten. "
        "De Basisregistratie Personen (BRP) levert de gegevens."
    )
    found = {(e["abbrev"], e["term"]) for e in extract_abbreviations(text, "https://x/doc", "doc.md")}
    assert ("VI", "Versleutelde Identiteit") in found
    assert ("BRP", "Basisregistratie Personen") in found


def test_rejects_false_positives():
    assert not is_valid_abbreviation("PRD", "productie")
    assert not is_valid_abbreviation("API", "zie de API voor details")


def test_expands_first_occurrence_case_insensitively():
    entries = {"VI": [{"abbrev": "VI", "term": "Versleutelde Identiteit", "source_url": "u"}]}
    query, applied = expand_query("Hoe wordt een vi versleuteld?", entries)
    assert query == "Hoe wordt een VI (Versleutelde Identiteit) versleuteld?"
    assert len(applied) == 1


def test_leaves_unknown_tokens_alone():
    query, applied = expand_query("Wat is EAD?", {})
    assert query == "Wat is EAD?"
    assert applied == []
