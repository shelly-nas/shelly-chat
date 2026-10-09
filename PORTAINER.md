# Deployen via Portainer

Deze handleiding beschrijft hoe je de RAG-chatbot uitrolt via een Portainer Stack. De indexering kan na deployment volledig via de webinterface worden gestart — een terminal is niet nodig.

## Vereisten

- Portainer CE/EE draaiend op de doelserver
- [Ollama](https://ollama.com) geïnstalleerd en actief **op de host** (niet in Docker)
- De vereiste modellen vooraf geladen:

```bash
ollama pull qwen3-embedding:latest
ollama pull gemma4:latest
```

- De repository-bestanden beschikbaar op de server (via `git clone` of handmatig kopiëren)

---

## Stap 1 — Maak een Stack aan in Portainer

1. Ga naar **Stacks → Add stack**
2. Kies **Repository** (als de code in Git staat) of **Web editor** (plak de inhoud van `docker-compose.yml`)
3. Geef de stack een naam, bijvoorbeeld `rag-chatbot`

---

## Stap 2 — Stel omgevingsvariabelen in

Portainer heeft een **Environment variables** sectie onderaan het stack-formulier. Voeg hier de variabelen toe die normaal in `.env` staan.

> De waarden `QDRANT_URL` en `OLLAMA_BASE_URL` worden automatisch overschreven door de `environment:`-sectie in `docker-compose.yml` — die hoef je hier niet in te vullen.

### Verplichte variabelen

Er zijn geen strikt verplichte omgevingsvariabelen — de standaardwaarden werken voor een lokale installatie. Voor een productie-installatie zijn de volgende variabelen aan te raden:

| Variabele | Voorbeeldwaarde | Toelichting |
|---|---|---|
| `LLM_SYSTEM_PROMPT` | `"Je bent een behulpzame assistent..."` | Aangepaste systeemprompt; standaard is een generieke Engelse prompt |
| `DATA_DIR` | `/app/data` | Map waar de documenten staan die geïndexeerd worden (standaard `/app/data`) |

### Optionele variabelen (overschrijf de standaardwaarden)

| Variabele | Standaard | Toelichting |
|---|---|---|
| `LLM_MODEL_NAME` | `gemma4:latest` | Ollama-model voor tekstgeneratie |
| `EMBED_MODEL` | `qwen3-embedding:latest` | Ollama-embeddingmodel |
| `LLM_SYSTEM_PROMPT` | *(ingebouwd)* | Aangepaste systeemprompt voor het LLM |
| `RETRIEVAL_TOP_K` | `20` | Aantal child-nodes opgehaald uit Qdrant |
| `RERANKER_TOP_N` | `5` | Aantal nodes doorgegeven aan het LLM na reranking |
| `AUTOMERGE_THRESHOLD` | `0.5` | Drempel voor het samenvoegen van child-nodes naar parent |
| `PARENT_CHUNK_SIZE` | `1500` | Tokengrootte van parent-chunks (na aanpassing: herindexeer volledig) |
| `VERBOSE` | `0` | Zet op `1` voor gedetailleerde logging per aanvraag |

---

## Stap 3 — Start de stack

Klik op **Deploy the stack**. Portainer bouwt de images en start de containers:

- `qdrant` start als eerste (Qdrant vector database)
- `generating` wacht tot Qdrant healthy is, daarna start de FastAPI-backend
- `frontend` wacht tot de backend healthy is, daarna start de Next.js-interface

Wacht totdat alle containers de status **running** hebben (doorgaans 1–2 minuten bij de eerste build).

---

## Stap 4 — Indexeer de documenten via de UI

Omdat je geen terminal op de remote server hebt, gebruik je de sync-knop in de webinterface:

1. Ga naar `http://<server-ip>:3000`
2. Klik op het **tandwiel-icoon** (⚙) rechts bovenaan
3. Klik op **Herindexeer** onder "Index synchroniseren"
4. Volg de voortgang in het statusbericht — dit kan een aantal minuten duren afhankelijk van het aantal documenten
5. Bij "Indexering voltooid" is de chatbot klaar voor gebruik

> Bij de allereerste keer zal de indexering ook `abbreviations.json` opbouwen uit de geïndexeerde documenten. Dit is automatisch.

---

## Service-overzicht

| Service | URL | Doel |
|---|---|---|
| Frontend | `http://<server-ip>:3000` | Chatinterface |
| Backend API | `http://<server-ip>:8000/docs` | FastAPI Swagger UI |
| Qdrant dashboard | `http://<server-ip>:6333/dashboard` | Vector database |
| Ollama | `http://<server-ip>:11434` | LLM- en embeddingserver (host) |

---

## Documenten toevoegen of bijwerken

Documenten worden gelezen uit de `data/`-map op de host (gemount als `/app/data` in de container). Voeg bestanden toe via de Portainer host-shell of via een gedeeld volume. Klik daarna op **Herindexeer** in de webinterface om de index bij te werken.

Ondersteunde bestandstypen: `.pdf`, `.docx`, `.html`, `.md`

Wanneer je `PARENT_CHUNK_SIZE` of `EMBED_MODEL` wijzigt, moet de Qdrant-collectie handmatig worden verwijderd vóór herindexering:

```bash
# Open de console van de 'generating'-container in Portainer:
# Containers → generating → Console → Connect

curl -X DELETE http://qdrant:6333/collections/chunks_child
rm -f /app/vector-db/docstore.json
```

Klik daarna op **Herindexeer** in de webinterface.

---

## Volumes

De stack gebruikt twee persistente volumes:

| Volume | Doel |
|---|---|
| `qdrant_storage` | Qdrant vector-opslag (beheerd door Docker) |
| `./vector-db` → `/app/vector-db` | `docstore.json`, `index-manifest.json`, `abbreviations.json` |
| `./data` → `/app/data` | Lokale bestanden (voor toekomstige upload-functionaliteit) |

> Zorg dat de directory `vector-db/` en `data/` op de host bestaan en schrijfbaar zijn voor de Docker-daemon.
