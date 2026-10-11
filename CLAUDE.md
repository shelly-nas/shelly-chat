# shelly-chat

Deze app volgt de shelly-nas standaarden uit de plugin **`shelly-fundamentals@shelly-nas`**
(repo `shelly-nas/shelly-fundamentals`). Gebruik de skills daaruit: `stack-voorkeuren`, `docker-traefik`,
`release-deploy`, `database-migraties`, `conventional-commits` en `design-richtlijnen`.

Is de plugin niet geladen, dan gelden in elk geval deze regels:

- **Stack:** React + Vite + TypeScript + MUI (`client/`), Python 3.12 + FastAPI (`server/`, poort 3000, alles onder
  `/api`, met `GET /api/health`), PostgreSQL 16 (`database/`).
- **Lokaal:** `docker-compose.yml` bouwt vanuit de broncode. **Productie:** `docker-compose.prod.yml`
  gebruikt alleen images met een gepinde `IMAGE_TAG`, achter Traefik op `shelly-network`, op
  `chat.shelly-nas.nl`.
- **Acc:** elke PR naar `main` wordt gedeployd naar `chat-acc.shelly-nas.nl` via
  `docker-compose.acc.yml` en `.github/workflows/acc.yml`, met een verse database met demodata.
  Houd `docker-compose.acc.yml` gelijk aan prod, op namen en host na.
- **Geheimen** staan alleen in `.env` (niet in git) en in GitHub-secrets. Een nieuwe env-variabele
  komt in `docker-compose.prod.yml` én `docker-compose.acc.yml`, in `env_file_content` van `deploy.yml` én `acc.yml`, en in `.env.example`.
- **Schemawijzigingen:** vóór 1.0.0 in `database/init.sql`. Daarna als idempotente, additieve
  migratie `server/migrations/NNN_*.sql`, en `init.sql` wordt meegewerkt.

## Commitberichten

Versiebeheer is automatisch: release-please leidt de volgende versie af uit de commitberichten op
`main`. **Elke commit is daarom een Conventional Commit.**

| Prefix | Bump |
|---|---|
| `fix:` | patch |
| `feat:` | minor |
| `feat!:` / `BREAKING CHANGE:` in de body | major |
| `perf:` `refactor:` `docs:` `test:` `ci:` `build:` `chore:` | geen |

Eén logische wijziging per commit. De samenvatting in de gebiedende wijs en met een kleine letter.
Pas nooit handmatig een versienummer aan.

## Architectuur van shelly-chat (wijkt af van een standaard shelly-app)

Een RAG-chatbot. **De NAS draait geen enkel model.** De taalmodellen draaien met Ollama op de computer
van de gebruiker, en de browser praat daar zelf mee.

| Map | Draait op | Rol |
|---|---|---|
| `client/` | NAS (nginx) | React + MUI. Roept `/api` op de NAS aan **én** Ollama op `localhost:11434` (`src/lib/ollama.ts`, `src/lib/rag.ts`) |
| `server/` | NAS | FastAPI zonder AI-modellen: afkortingen (`/api/expand`), vectorzoeken + auto-merge (`/api/retrieve`), gesprekken, index-API (`/api/index/*`, met `INDEX_TOKEN`), en documenten lezen, uitpakken + knippen (`/api/index/files`, `/api/index/prepare`, LlamaIndex' tekstsplitter), originelen serveren (`/api/files/…`) |
| `database/` | NAS | Postgres 16 + **pgvector** (in `database/Dockerfile` gebouwd op `postgres:16-alpine`, zodat uid 70 blijft). CI gebruikt `pgvector/pgvector:0.8.0-pg16`; houd de versies gelijk |
| `host/` | computer met Ollama | CLI-indexer en RAGAS-evaluatie. Geen Docker, niet in de deploy |

Vraagflow: `POST /api/expand` → Ollama `/api/embed` (model van de index, `GET /api/config`) →
`POST /api/retrieve` → Ollama `/api/chat` (streaming NDJSON) → `POST /api/conversations`.
`host/rag.py` is dezelfde flow in Python. Wijzig je de prompt of de stappen, doe dat dan in beide.

Indexflow (scherm Index, `client/src/lib/indexer.ts`): `GET /api/index/files` (NAS somt de documenten in de bronnen op)
→ `POST /api/index/prepare` (NAS leest, pakt uit, hasht, knipt; ongewijzigd stopt hier) → Ollama `/api/embed` voor
de leaves → `PUT /api/index/documents`.
`host/indexing/indexer.py` is dezelfde run als CLI. Wijzig je de regels (reset, verwijderen), doe dat dan in beide.

Documenten staan in de documentenmap op de NAS (`DOCUMENTS_DIR`, alleen-lezen gemount op `/data/documents`).
Bronnen en `file_path`s zijn altijd relatief aan die map; ga voor elk pad door `app/files.py` (`resolve`), dat
paden buiten de map weigert.

Regels:
- Zet niets op de server dat een model laadt (geen torch, sentence-transformers of Ollama-calls). De tekstsplitter van llama-index-core is geen model en mag.
- Het index-token van een gebruiker blijft in de browser (localStorage); sla het niet op de NAS op.
- De `embedding`-kolom heeft geen vaste dimensie. Een ander embeddingmodel betekent een reset door de indexer, geen migratie.
- Ollama staat alleen origins toe die in `OLLAMA_ORIGINS` staan. Nieuwe hostnamen moeten in de README-instructies.
