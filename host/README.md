# host/: tools naast Ollama

Indexeren gaat normaal via het scherm **Index** in de app. Wat hier staat is voor de terminal: dezelfde
indexeerrun als CLI (voor scripts of een geplande taak), een vraag stellen zonder browser, en de
evaluatie. Het draait op een computer met Ollama, en met de VPN aan als GitLab daarachter zit.

| Onderdeel | Doel |
|---|---|
| `indexing/` | CLI-indexer: dezelfde run als het Index-scherm |
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
cp .env.example .env    # vul SHELLY_CHAT_URL, INDEX_TOKEN en GITLAB_PAT in
ollama pull qwen3-embedding:latest
```

## Indexeren vanuit de terminal

```bash
python -m indexing.indexer                        # incrementeel: alleen nieuw en gewijzigd
python -m indexing.indexer --full-reindex         # index leegmaken en alles opnieuw
python -m indexing.indexer --build-abbreviations  # alleen de afkortingen opnieuw opbouwen
```

De run is gelijk aan die van het Index-scherm (`client/src/lib/indexer.ts`):

1. De **bronnen** en de **chunkinstellingen** komen van de NAS, en de bronnen beheer je op het
   Index-scherm. Het embeddingmodel komt uit `EMBED_MODEL`. Wijkt het model, de dimensie of de
   chunkinstelling af van waarmee de index gebouwd is, dan wordt de index geleegd en opnieuw opgebouwd.
2. Elk document wordt uit GitLab gehaald en naar de NAS gestuurd (`POST /api/index/prepare`). De NAS
   haalt de tekst eruit (ook uit PDF en DOCX), hasht die en knipt hem in parents en leaves. Een
   ongewijzigd document stopt hier.
3. De leaves worden met Ollama geëmbed en opgeslagen (`PUT /api/index/documents`). De NAS haalt er
   meteen de afkortingen uit.
4. Documenten die niet meer in GitLab staan, worden verwijderd, maar alleen als elke bron gelezen kon worden.

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
| `GITLAB_PAT` | leeg | Personal Access Token met `read_api` |

Chunkgroottes stel je in op de NAS (`PARENT_CHUNK_SIZE`, `CHILD_CHUNK_SIZE`, `PARENT_CHUNK_OVERLAP`).
Grotere parents geven het model meer context per bron, maar ook meer ruis. Kleinere leaves zoeken
preciezer. `AUTOMERGE_THRESHOLD` bepaalt vanaf welk deel van de gevonden leaves de hele parent wordt
meegegeven.

Ondersteunde bestanden in repositories: `.md`, `.adoc`, `.pdf`, `.docx` en `.doc` (best-effort). Elk
document krijgt een `source_url` naar GitLab. Daarnaar linkt de knop **Openen** bij een bron in de app.

## Een vraag stellen vanuit de terminal

```bash
python rag.py "Hoe werkt het Renovate-proces?"
```

## Evaluatie

```bash
pip install -r requirements-eval.txt
pytest tests/eval -v -s           # of: python -m tests.eval.test_rag_eval
```

De vragen staan in `tests/eval/eval_dataset.json`. Vul `ground_truth` in om ook context precision en
recall te meten. Drempels via `EVAL_*_THRESHOLD`.
