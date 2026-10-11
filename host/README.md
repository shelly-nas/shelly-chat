# host/: tools naast Ollama

Indexeren gaat normaal via het scherm **Indexen** in de app. Wat hier staat is voor de terminal: dezelfde
indexeerrun als CLI (voor scripts of een geplande taak), een vraag stellen zonder browser, en de
evaluatie. Het draait op een computer met Ollama; de documenten zelf blijven op de NAS.

| Onderdeel | Doel |
|---|---|
| `indexing/` | CLI-indexer: dezelfde run als het Indexen-scherm |
| `rag.py` | Dezelfde vraag-en-antwoordpijplijn als de browser |
| `tests/unit/` | Unittests van de indexer (draaien in CI) |
| `tests/eval/` | RAGAS-evaluatie van de antwoordkwaliteit (handmatig, traag) |
| `docs/` | Ollama installeren op Rocky Linux (Sapphire Rapids) |

## Installeren

Python 3.12:

```bash
cd host
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # vul SHELLY_CHAT_URL en INDEX_TOKEN in
ollama pull qwen3-embedding:latest
```

## Indexeren vanuit de terminal

```bash
python -m indexing.indexer                        # alle indexen, incrementeel: alleen nieuw en gewijzigd
python -m indexing.indexer --index "Mijn BV"      # alleen deze index (naam, hoofdletters maakt niet uit)
python -m indexing.indexer --full-reindex         # alles leegmaken en alle indexen opnieuw
python -m indexing.indexer --build-abbreviations  # alleen de afkortingen opnieuw opbouwen
```

De run is gelijk aan die van het Indexen-scherm (`client/src/lib/indexer.ts`):

1. De **indexen**, hun **bronnen** en **ignore-patronen** en de **chunkinstellingen** komen van de NAS.
   Indexen en bronnen beheer je op het Indexen-scherm. Het embeddingmodel komt uit `EMBED_MODEL`. Wijkt het model, de dimensie of de
   chunkinstelling af van waarmee de index gebouwd is, dan worden alle indexen geleegd en opnieuw opgebouwd.
2. Per index somt de NAS de documenten in de bronnen op, na de ignore-patronen (`GET /api/indexes/{id}/files`). Per document leest de NAS het
   bestand, haalt de tekst eruit (ook uit PDF en DOCX), hasht die en knipt hem in parents en leaves
   (`POST /api/index/prepare`). Een ongewijzigd document (bijvoorbeeld al geëmbed voor een andere index) komt direct in de index en stopt hier.
3. De leaves worden met Ollama geëmbed en opgeslagen (`PUT /api/index/documents`). De NAS haalt er
   meteen de afkortingen uit.
4. Documenten die niet meer in de bronnen staan, gaan uit de index (`POST /api/indexes/{id}/prune`), maar alleen als elke bron
   gelezen kon worden. Een document dat in geen enkele index meer zit, wordt verwijderd.

Omdat de NAS knipt, maken de app en de CLI precies dezelfde chunks. Na een run vanuit de app ziet
de CLI dus alles als ongewijzigd, en andersom.

## Configuratie (`host/.env`)

| Variabele | Standaard | Betekenis |
|---|---|---|
| `SHELLY_CHAT_URL` | `http://localhost:3000` | De shelly-chat-server: prod `http://chat.shelly-nas.nl`, acc `http://chat-acc.shelly-nas.nl` |
| `INDEX_TOKEN` | leeg | Gelijk aan `INDEX_TOKEN` op de NAS |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama op deze computer |
| `EMBED_MODEL` | `qwen3-embedding:latest` | Embeddingmodel; vragen in de app gebruiken daarna hetzelfde model |
| `EMBED_BATCH_SIZE` | `16` | Chunks per embed-aanroep |

Chunkgroottes stel je in op de NAS (`PARENT_CHUNK_SIZE`, `CHILD_CHUNK_SIZE`, `PARENT_CHUNK_OVERLAP`).
Grotere parents geven het model meer context per bron, maar ook meer ruis. Kleinere leaves zoeken
preciezer. `AUTOMERGE_THRESHOLD` bepaalt vanaf welk deel van de gevonden leaves de hele parent wordt
meegegeven.

Ondersteunde bestanden: `.md`, `.adoc`, `.txt`, `.pdf`, `.docx` en `.doc` (best-effort). Bronnen zijn
paden relatief aan de documentenmap op de NAS (zie de README in de root).

## Een vraag stellen vanuit de terminal

```bash
python rag.py "Mijn BV" "Hoe werkt het Renovate-proces?"   # eerst de index, dan de vraag
```

## Evaluatie

```bash
pip install -r requirements-eval.txt
pytest tests/eval -v -s           # of: python -m tests.eval.test_rag_eval
```

De vragen staan in `tests/eval/eval_dataset.json`. Vul `ground_truth` in om ook context precision en
recall te meten. De index kies je met `EVAL_INDEX` (standaard "Alle documenten"), drempels via
`EVAL_*_THRESHOLD`.
