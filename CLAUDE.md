# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- The graph shows structure and relationships, but NOT runtime behavior or inline logic. For questions like "does X happen automatically during Y?" always read the actual source function — don't infer from node names or community membership alone.

## Architecture Overview

This is a local RAG (Retrieval-Augmented Generation) system for searching organizational documents using locally-running LLMs. It consists of three independently deployable services:

```
indexing/      — CLI tool: fetches documents from GitLab, chunks, embeds, stores in Qdrant
generating/    — FastAPI backend: query expansion → embed → retrieve → rerank → stream LLM
chat-app/      — Next.js frontend: proxies SSE from backend, renders streamed responses
vector-db/     — Persistent data: docstore.json (parent nodes), abbreviations.json, .indexing.lock
```

**Ollama runs on the host machine** (never in Docker) at `localhost:11434`. The three services run in Docker via `docker-compose.yml`. The indexer runs locally and connects to Qdrant in Docker.

### RAG Retrieval Strategy

The retrieval pipeline uses **Hierarchical Auto-Merging** (LlamaIndex):
1. Documents are chunked into parent nodes (`PARENT_CHUNK_SIZE` tokens, default 1500) and child nodes (`CHILD_CHUNK_SIZE = PARENT // 4`)
2. Only child node vectors are stored in Qdrant; parent nodes live in `vector-db/docstore.json`
3. At query time: embed query → top-K child similarity search → AutoMergingRetriever (promotes child groups to parent when ≥ `AUTOMERGE_THRESHOLD` fraction of siblings retrieved) → SentenceTransformerRerank → top-N to LLM
4. After retrieval, the embed model is unloaded from Ollama before the LLM loads — they run sequentially to fit in limited VRAM

### SSE Event Protocol

The `/api/chat` endpoint streams Server-Sent Events in this order:
1. `event: expansions` — list of abbreviation expansions applied to the query
2. `event: contexts` — retrieved document chunks with metadata
3. `event: token` — individual LLM response tokens
4. `event: metrics` — wall time and model name
5. `event: done` — stream complete
6. `event: error` — on any failure

The Next.js route at `chat-app/src/app/api/chat/route.ts` proxies this SSE stream from the FastAPI backend.

## Development Commands

### Python backend (indexing + generating)

```bash
# Setup
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Run generating service locally
uvicorn generating.app:app --port 8000 --reload

# Run indexer (sources configured via .env)
python -m indexing.indexer
python -m indexing.indexer --full-reindex        # after changing chunk sizes or embed model
python -m indexing.indexer --build-abbreviations # backfill abbreviations without re-indexing

# Run tests (requires FastAPI service running)
pytest tests/ -v
pytest tests/test_rag_eval.py -v -s -m slow      # end-to-end RAGAS evaluation (slow)
```

### Next.js frontend

```bash
cd chat-app
npm install
npm run dev      # dev server at http://localhost:3000
npm run build
npm run lint
```

### Docker

```bash
docker compose up -d          # start all services
docker compose up -d generating  # start only backend
docker compose logs -f generating
```

## Environment Variables

All config is loaded from `.env` in the project root. Key variables:

| Variable | Default | Notes |
|---|---|---|
| `GITLAB_WIKI_URLS` | — | Comma-separated GitLab wiki URLs to index |
| `GITLAB_REPO_URLS` | — | Comma-separated GitLab repo URLs to index |
| `GITLAB_PAT` | — | GitLab Personal Access Token (`read_wiki`, `read_repository` scopes) |
| `LLM_MODEL_NAME` | `gemma4:latest` | Ollama model for generation |
| `EMBED_MODEL` | `qwen3-embedding:latest` | Ollama embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Host address differs inside Docker: `host.docker.internal:11434` |
| `QDRANT_URL` | `http://localhost:6333` | In Docker: `http://qdrant:6333` |
| `LLM_SYSTEM_PROMPT` | — | Override the system prompt for the LLM |
| `VERBOSE` | `0` | Set to `1` for detailed per-request retrieval logging |
| `RETRIEVAL_TOP_K` | `20` | Number of child nodes fetched from Qdrant |
| `RERANKER_TOP_N` | `5` | Nodes passed to LLM after reranking |

## Key Files

- [generating/app.py](generating/app.py) — FastAPI app: all endpoints, retrieval pipeline, session management, Ollama model lifecycle
- [generating/query_expander.py](generating/query_expander.py) — Abbreviation expansion from `abbreviations.json`; the legacy LLM-based expansion functions at the bottom are unused
- [indexing/indexer.py](indexing/indexer.py) — Document ingestion: GitLab fetching, HierarchicalNodeParser, incremental sync via Qdrant payloads, abbreviation extraction
- [indexing/change_detection.py](indexing/change_detection.py) — SHA-256 change detection via `content_hash`/`file_path` in Qdrant point payloads (no manifest file)
- [indexing/version_stamp.py](indexing/version_stamp.py) — Config version stamp in the `index_meta` Qdrant collection; drift triggers automatic full reindex
- [indexing/lock.py](indexing/lock.py) — flock on `vector-db/.indexing.lock`: exclusive during indexing, shared during docstore reload
- [vector-db/abbreviations.json](vector-db/abbreviations.json) — Built at index time; used at query time for fast dict-based expansion
- [chat-app/src/app/page.tsx](chat-app/src/app/page.tsx) — Main chat UI; handles SSE parsing, session state, query expansion toggle

## Incremental Indexing

On each run the indexer scrolls Qdrant once to read back each indexed file's `file_path` and `content_hash` payloads — **there is no manifest file**; Qdrant is the single source of truth:
- **New/changed** documents are re-embedded and upserted
- **Deleted** documents are cleaned from Qdrant and docstore
- **Unchanged** documents are skipped (no embedding calls)

Changing `PARENT_CHUNK_SIZE`, `CHILD_CHUNK_SIZE`, `PARENT_CHUNK_OVERLAP`, or `EMBED_MODEL` is detected automatically via the `index_meta` version stamp and triggers a full rebuild; `--full-reindex` forces one on demand. The reset drops both Qdrant collections and the docstore, then writes the new stamp immediately so an interrupted rebuild resumes incrementally.
