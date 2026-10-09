# Graph Report - .  (2026-07-15)

## Corpus Check
- Corpus is ~25,367 words - fits in a single context window. You may not need a graph.

## Summary
- 573 nodes · 711 edges · 53 communities (47 shown, 6 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 52 edges (avg confidence: 0.81)
- Token cost: 83,925 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Chat UI Frontend|Chat UI Frontend]]
- [[_COMMUNITY_Chat API & Model Lifecycle|Chat API & Model Lifecycle]]
- [[_COMMUNITY_Indexing API & Reload|Indexing API & Reload]]
- [[_COMMUNITY_Indexing API Docs (README)|Indexing API Docs (README)]]
- [[_COMMUNITY_Indexing Run Logging & Reload|Indexing Run Logging & Reload]]
- [[_COMMUNITY_Indexer Console Output|Indexer Console Output]]
- [[_COMMUNITY_Indexer Setup Guide|Indexer Setup Guide]]
- [[_COMMUNITY_Architecture Diagrams (README)|Architecture Diagrams (README)]]
- [[_COMMUNITY_Architecture Overview (CLAUDE.md)|Architecture Overview (CLAUDE.md)]]
- [[_COMMUNITY_Frontend Architecture Docs|Frontend Architecture Docs]]
- [[_COMMUNITY_RAG Strategy Rationale Docs|RAG Strategy Rationale Docs]]
- [[_COMMUNITY_Change Detection (SHA-256)|Change Detection (SHA-256)]]
- [[_COMMUNITY_Document Parsing (PDFDOCX)|Document Parsing (PDF/DOCX)]]
- [[_COMMUNITY_Portainer Deployment Guide|Portainer Deployment Guide]]
- [[_COMMUNITY_Indexer Pipeline Core|Indexer Pipeline Core]]
- [[_COMMUNITY_UI-Triggered Indexing Spec|UI-Triggered Indexing Spec]]
- [[_COMMUNITY_Full Reindex & Version Stamp|Full Reindex & Version Stamp]]
- [[_COMMUNITY_Cleanup (Stale PointsNodes)|Cleanup (Stale Points/Nodes)]]
- [[_COMMUNITY_Deployment & Task Docs|Deployment & Task Docs]]
- [[_COMMUNITY_Abbreviation Query Expansion|Abbreviation Query Expansion]]
- [[_COMMUNITY_RAGAS Evaluation Tests|RAGAS Evaluation Tests]]
- [[_COMMUNITY_GitLab Wiki Fetcher|GitLab Wiki Fetcher]]
- [[_COMMUNITY_Abbreviation Validation Logic|Abbreviation Validation Logic]]
- [[_COMMUNITY_Next.js Root Layout|Next.js Root Layout]]
- [[_COMMUNITY_Select UI Component|Select UI Component]]
- [[_COMMUNITY_Multi-Source Indexing Pipeline|Multi-Source Indexing Pipeline]]
- [[_COMMUNITY_Chat Retrieval Strategy|Chat Retrieval Strategy]]
- [[_COMMUNITY_Test Suite Overview|Test Suite Overview]]
- [[_COMMUNITY_Test Running Guide|Test Running Guide]]
- [[_COMMUNITY_Test Debugging Guide|Test Debugging Guide]]
- [[_COMMUNITY_RAG Evaluation Framework|RAG Evaluation Framework]]
- [[_COMMUNITY_Performance Benchmarking|Performance Benchmarking]]
- [[_COMMUNITY_Pytest Fixtures & Utilities|Pytest Fixtures & Utilities]]
- [[_COMMUNITY_CICD Test Integration|CI/CD Test Integration]]
- [[_COMMUNITY_LlamaIndex LLM Wrapper|LlamaIndex LLM Wrapper]]
- [[_COMMUNITY_Test Service Health Check|Test Service Health Check]]
- [[_COMMUNITY_Evaluation Report Generation|Evaluation Report Generation]]
- [[_COMMUNITY_Test Category Taxonomy|Test Category Taxonomy]]
- [[_COMMUNITY_PostCSS Config|PostCSS Config]]
- [[_COMMUNITY_ESLint Config|ESLint Config]]
- [[_COMMUNITY_Next.js Config|Next.js Config]]
- [[_COMMUNITY_AMX Segfault Workaround (VM.md)|AMX Segfault Workaround (VM.md)]]
- [[_COMMUNITY_Indexer Safe Path Helper|Indexer Safe Path Helper]]

## God Nodes (most connected - your core abstractions)
1. `cn()` - 27 edges
2. `_run_pipeline()` - 25 edges
3. `_run_pipeline` - 17 edges
4. `run_all_sources_pipeline()` - 11 edges
5. `build_abbreviations_from_docstore()` - 11 edges
6. `Testing Framework & Evaluation` - 11 edges
7. `fetch_repo_documents()` - 10 edges
8. `log_info()` - 10 edges
9. `_embed_and_upsert()` - 10 edges
10. `Document Indexering` - 10 edges

## Surprising Connections (you probably didn't know these)
- `Hierarchical Auto-Merging Retrieval Strategy` --semantically_similar_to--> `Sequential Embed then LLM Model Loading`  [INFERRED] [semantically similar]
  indexing/README.md → CLAUDE.md
- `Incremental Indexing via SHA-256 Manifest` --semantically_similar_to--> `Hallucination Prevention Strategy`  [INFERRED] [semantically similar]
  indexing/README.md → generating/README.md
- `chat (POST /api/chat)` --rationale_for--> `RAG Retrieval Strategy (Hierarchical Auto-Merging)`  [EXTRACTED]
  generating/app.py → CLAUDE.md
- `chat (POST /api/chat)` --rationale_for--> `Ophaalstrategie: Hiërarchisch Auto-Merging`  [EXTRACTED]
  generating/app.py → indexing/README.md
- `chat (POST /api/chat)` --references--> `SSE Event Protocol`  [EXTRACTED]
  generating/app.py → CLAUDE.md

## Hyperedges (group relationships)
- **Incremental sync via Qdrant payloads (no manifest)** — change_detection_fetch_indexed_hashes, change_detection_classify_documents, cleanup_cleanup_file_path, indexer_run_pipeline, indexing_readme_no_manifest_rationale [INFERRED 0.90]
- **UI-triggered indexing run end-to-end** — route_index_post, app_trigger_index, app_reload_retrieval_state, lock_indexing_lock [EXTRACTED 0.85]
- **Config drift detection triggering full reindex** — version_stamp_read_stamp, version_stamp_write_stamp, indexer_config_stamp, indexer_do_full_reindex_reset, claude_md_incremental_indexing [INFERRED 0.85]

## Communities (53 total, 6 thin omitted)

### Community 0 - "Chat UI Frontend"
Cohesion: 0.07
Nodes (43): ExpansionSource, Message, SourceContext, FormattedMessage(), FormattedMessageProps, QueryExpansionBadgeProps, QueryExpansionBubble(), QueryExpansionBubbleProps (+35 more)

### Community 1 - "Chat API & Model Lifecycle"
Cohesion: 0.05
Nodes (43): BaseModel, ChatRequest, cleanup_all_models(), get_file_content(), _get_session(), index_status(), IndexRequest, list_loaded_ollama_models() (+35 more)

### Community 2 - "Indexing API & Reload"
Cohesion: 0.05
Nodes (47): index_status (GET /api/index/status), reload_retrieval_state, trigger_index (POST /api/index), classify_documents, compute_hash, fetch_indexed_hashes, Incremental Indexing (Qdrant as single source of truth), cleanup_file_path (+39 more)

### Community 3 - "Indexing API Docs (README)"
Cohesion: 0.08
Nodes (23): API Endpoints, `/api/index` request body, `/api/index/status` response, Belangrijkste functies, Chatgeschiedenis, code:block1 (generating/), code:mermaid (sequenceDiagram), code:block3 (event: expansions   — toegepaste afkortingsuitbreidingen) (+15 more)

### Community 4 - "Indexing Run Logging & Reload"
Cohesion: 0.1
Nodes (17): Reload docstore and rebuild index after indexing completes., Reload docstore and rebuild index after indexing completes., reload_retrieval_state(), _append_log(), _CapturingStream, Background indexing runner for the generating service.  Wraps run_indexing_pipel, Start indexing in a background thread.      Raises RuntimeError if a run is alre, Start indexing in a background thread.      Raises RuntimeError if a run is alre (+9 more)

### Community 5 - "Indexer Console Output"
Cohesion: 0.1
Nodes (20): Colors, log_success(), log_warn(), Console output utilities for the indexing module., build_abbreviations_from_docstore(), _embed_and_upsert(), _extract_abbreviations(), IndexingConfig (+12 more)

### Community 6 - "Indexer Setup Guide"
Cohesion: 0.1
Nodes (20): 1. Stel de bronnen in via `.env`, 2. Start de indexer, code:mermaid (flowchart), code:mermaid (flowchart), code:bash (GITLAB_WIKI_URLS='), Configuratie, Document Indexering, Effect van numerieke waarden (+12 more)

### Community 7 - "Architecture Diagrams (README)"
Cohesion: 0.12
Nodes (16): Belangrijkste functies, code:mermaid (flowchart TB), code:block2 (├── indexing/                   # Documentverwerking en embe), code:bash (ollama pull qwen3-embedding:latest), code:bash (docker compose up -d  # Start Qdrant + Generation API + Fron), code:mermaid (sequenceDiagram), Installatie, Moduledocumentatie (+8 more)

### Community 8 - "Architecture Overview (CLAUDE.md)"
Cohesion: 0.12
Nodes (15): Architecture Overview, code:block1 (indexing/      — CLI tool: fetches documents from GitLab, ch), code:bash (# Setup), code:bash (cd chat-app), code:bash (docker compose up -d          # start all services), Development Commands, Docker, Environment Variables (+7 more)

### Community 9 - "Frontend Architecture Docs"
Cohesion: 0.12
Nodes (15): Architectuur, Bronweergave, Chat Interface (Next.js), Chatinterface, code:block1 (chat-app/), code:mermaid (flowchart LR), code:bash (cd chat-app), code:bash (docker compose up -d) (+7 more)

### Community 10 - "RAG Strategy Rationale Docs"
Cohesion: 0.22
Nodes (16): Abbreviation Expansion via Dictionary Lookup, CLAUDE.md Architecture Guide, Text Generation Service README, Hallucination Prevention Strategy, Hierarchical Auto-Merging Retrieval Strategy, Incremental Indexing via SHA-256 Manifest, Document Indexing README, Ollama Runs on Host (Not in Docker) (+8 more)

### Community 11 - "Change Detection (SHA-256)"
Cohesion: 0.18
Nodes (13): classify_documents(), compute_hash(), fetch_indexed_hashes(), Change detection via Qdrant point payloads: track indexed files without a manife, Scroll the full collection once, return {file_path: content_hash}.      Deduplic, Classify fetched documents against the hashes stored in Qdrant.      Documents m, Remove all abbreviation entries belonging to the given source URLs., Remove all abbreviation entries belonging to the given source URLs. (+5 more)

### Community 12 - "Document Parsing (PDF/DOCX)"
Cohesion: 0.18
Nodes (12): parse_docx_bytes(), parse_pdf_bytes(), Plain-text extraction from binary document formats.  Used by GitLab fetchers whe, Extract text from a PDF given raw bytes., Extract text from a DOCX (or .doc) file given raw bytes.      python-docx handle, fetch_repo_documents(), _file_ext(), _parse_repo_url() (+4 more)

### Community 13 - "Portainer Deployment Guide"
Cohesion: 0.14
Nodes (13): code:bash (ollama pull qwen3-embedding:latest), code:bash (# Open de console van de 'generating'-container in Portainer), Deployen via Portainer, Documenten toevoegen of bijwerken, Optionele variabelen (overschrijf de standaardwaarden), Service-overzicht, Stap 1 — Maak een Stack aan in Portainer, Stap 2 — Stel omgevingsvariabelen in (+5 more)

### Community 14 - "Indexer Pipeline Core"
Cohesion: 0.18
Nodes (11): _config_stamp(), from_env(), _load_docstore(), _parse_url_list(), LlamaIndex-based document ingestion pipeline.  Fetches content from GitLab (wiki, The config values that require a full reindex when they change., Split a comma-separated .env URL list, skipping blank entries and     lines comm, Fetch supported documents from a GitLab repository and index them.      Supporte (+3 more)

### Community 15 - "UI-Triggered Indexing Spec"
Cohesion: 0.15
Nodes (12): Indexering via de UI triggeren, Interface-optie A — Sync-knop (eenvoudig), Interface-optie B — Uploadinterface, Interface-optie C — Beide (aanbevolen), Kwaliteitseisen, Ontwerpkeuzes (te bepalen vóór implementatie), Ontwikkeltaken, Probleemomschrijving (+4 more)

### Community 16 - "Full Reindex & Version Stamp"
Cohesion: 0.17
Nodes (11): _do_full_reindex_reset(), _manifest_path(), Drop Qdrant collection, delete docstore and manifest for a clean slate., Drop Qdrant collections and delete local files for a clean slate., delete_stamp(), Version stamp: detect embed-model/chunk-config drift via Qdrant.  A dedicated `i, Return the stored config stamp, or None if no stamp exists yet., Upsert the single stamp point, creating the collection if needed.      The colle (+3 more)

### Community 17 - "Cleanup (Stale Points/Nodes)"
Cohesion: 0.24
Nodes (10): cleanup_file_path(), delete_docstore_nodes_by_file_path(), delete_qdrant_points_by_file_path(), Cleanup helpers: remove stale Qdrant points and docstore nodes by file_path.  Ca, Delete all Qdrant points whose file_path payload matches file_path.      Returns, Delete all nodes from the docstore where metadata.file_path matches.      Return, Delete all nodes from the docstore where metadata.file_path matches.      Return, Remove all Qdrant points and docstore nodes for a given file_path. (+2 more)

### Community 18 - "Deployment & Task Docs"
Cohesion: 0.25
Nodes (11): Chat App (Next.js) README, Docker Compose Service Definitions, Task 1: /api/index Backend Endpoint, Task 2: Frontend Sync Button (Settings Panel), Task 3: File Upload Interface, Portainer Deployment Guide, Python Dependencies (requirements.txt), Frontend (Next.js) Docker Service (+3 more)

### Community 19 - "Abbreviation Query Expansion"
Cohesion: 0.22
Nodes (9): apply_expansions(), expand_query_from_dict(), load_abbreviations(), Query expansion via abbreviation dictionary lookup.  Detects domain-specific abb, Legacy Phase 1: retrieve context text per detected abbreviation. No longer calle, Legacy Phase 2: ask the LLM for definitions and enrich the query. No longer call, Load abbreviations.json with mtime-based cache invalidation., Expand abbreviations in query using the pre-built dictionary.      Returns (enri (+1 more)

### Community 20 - "RAGAS Evaluation Tests"
Cohesion: 0.27
Nodes (9): _build_ragas_llm_and_embeddings(), _ragas_evaluate(), RAG evaluation using RAGAS metrics against a FastAPI endpoint.  Metrics always e, Wrap local Ollama models for RAGAS. Skips the test if dependencies are     missi, Build a RAGAS EvaluationDataset and run the configured metrics.      Args:, End-to-end RAG quality gate.      Runs every entry in tests/eval_dataset.json th, Run the full RAG pipeline for one question via FastAPI HTTP endpoint.      Retur, _run_pipeline() (+1 more)

### Community 21 - "GitLab Wiki Fetcher"
Cohesion: 0.22
Nodes (9): fetch_wiki_documents(), _parse_wiki_url(), GitLab wiki fetcher.  Retrieves all markdown pages from a GitLab wiki via the RE, Return (base_url, project_path) extracted from a GitLab wiki URL., Fetch all markdown wiki pages from a GitLab wiki.      Authentication is via a P, Fetch all markdown pages from a GitLab wiki and index them.      Each indexed do, Fetch all markdown pages from a GitLab wiki and index them.      Each indexed do, Fetch all markdown pages from a GitLab wiki and index them.      Each indexed do (+1 more)

### Community 22 - "Abbreviation Validation Logic"
Cohesion: 0.22
Nodes (9): _is_valid_abbreviation(), Strip leading stop words (articles, prepositions) that are never part of an abbr, Return (letter_upper, char_pos) at word-initial and CamelCase boundaries., Strip leading stop words (articles, prepositions) that are never part of an abbr, Validate that abbrev is a genuine abbreviation of term.      - Rejects if abbrev, Return (letter_upper, char_pos) at word-initial and CamelCase boundaries., Validate that abbrev is a genuine abbreviation of term.      - Rejects if abbrev, _strip_term() (+1 more)

### Community 23 - "Next.js Root Layout"
Cohesion: 0.29
Nodes (5): geistMono, geistSans, metadata, ThemeProvider(), ThemeProviderProps

### Community 24 - "Select UI Component"
Cohesion: 0.25
Nodes (7): SelectContent, SelectItem, SelectLabel, SelectScrollDownButton, SelectScrollUpButton, SelectSeparator, SelectTrigger

### Community 25 - "Multi-Source Indexing Pipeline"
Cohesion: 0.25
Nodes (8): Fetch all configured GitLab sources and index them in one pass.      Collects do, Fetch all configured GitLab sources and index them in one pass.      Collects do, Fetch all configured GitLab sources and index them in one pass.      Collects do, Entry point used by generating.indexing_runner to trigger a full index run., Entry point used by generating.indexing_runner to trigger a full index run., Entry point used by generating.indexing_runner to trigger a full index run., run_all_sources_pipeline(), run_indexing_pipeline()

### Community 26 - "Chat Retrieval Strategy"
Cohesion: 0.32
Nodes (8): chat (POST /api/chat), _get_session, list_loaded_ollama_models, unload_ollama_model, wait_for_model_unload, RAG Retrieval Strategy (Hierarchical Auto-Merging), SSE Event Protocol, Ophaalstrategie: Hiërarchisch Auto-Merging

### Community 27 - "Test Suite Overview"
Cohesion: 0.29
Nodes (6): code:block1 (tests/), Continuous Monitoring, Directory Contents, Integration with Development Workflow, Quality Gates, Testing Framework & Evaluation

### Community 28 - "Test Running Guide"
Cohesion: 0.29
Nodes (7): code:bash (# Activate virtual environment), code:bash (# Run comprehensive RAG evaluation), code:bash (# Test-specific environment variables), Prerequisites, Quick Start, Running Tests, Test Configuration

### Community 29 - "Test Debugging Guide"
Cohesion: 0.29
Nodes (7): code:python (def test_service_health():), code:python (def test_retrieval_quality():), code:bash (# Run tests with maximum verbosity), code:python (import logging), Common Test Failures, Debugging Failed Tests, Test Debugging Tools

### Community 30 - "RAG Evaluation Framework"
Cohesion: 0.33
Nodes (6): code:json ({), code:python (# tests/test_rag_eval.py), Evaluation Dataset, Evaluation Metrics, RAG Evaluation Framework, Running Evaluations

### Community 31 - "Performance Benchmarking"
Cohesion: 0.4
Nodes (5): Benchmark Categories, code:python (def test_indexing_performance(benchmark):), code:python (def test_query_performance(benchmark):), code:python (import psutil), Performance Benchmarking

### Community 32 - "Pytest Fixtures & Utilities"
Cohesion: 0.4
Nodes (5): code:python (import pytest), code:python (# tests/utils.py), Pytest Configuration (`conftest.py`), Test Fixtures & Utilities, Test Utilities

### Community 33 - "CI/CD Test Integration"
Cohesion: 0.4
Nodes (5): code:yaml (name: Test Suite), code:yaml (repos:), Continuous Testing, GitHub Actions Integration, Pre-commit Hooks

### Community 34 - "LlamaIndex LLM Wrapper"
Cohesion: 0.5
Nodes (3): get_llm(), LlamaIndex Ollama LLM wrapper for the generating/ service.  Provides a pre-confi, Return a configured LlamaIndex Ollama LLM instance.

### Community 36 - "Evaluation Report Generation"
Cohesion: 0.5
Nodes (4): Automated Report Generation, code:python (def generate_evaluation_report(results: List[Dict]) -> Dict:), code:json ({), Evaluation Reports

### Community 37 - "Test Category Taxonomy"
Cohesion: 0.5
Nodes (4): 1. Unit Tests, 2. Integration Tests, 3. RAG Evaluation, Test Categories

## Ambiguous Edges - Review These
- `chat (POST /api/chat)` → `_get_session`  [AMBIGUOUS]
  generating/app.py · relation: references

## Knowledge Gaps
- **267 isolated node(s):** `Background indexing runner for the generating service.  Wraps run_indexing_pipel`, `Start indexing in a background thread.      Raises RuntimeError if a run is alre`, `Write to both real stdout and the log buffer.`, `Query expansion via abbreviation dictionary lookup.  Detects domain-specific abb`, `Load abbreviations.json with mtime-based cache invalidation.` (+262 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `chat (POST /api/chat)` and `_get_session`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `_run_pipeline()` connect `Change Detection (SHA-256)` to `Indexing Run Logging & Reload`, `Indexer Console Output`, `Indexer Pipeline Core`, `Full Reindex & Version Stamp`, `Cleanup (Stale Points/Nodes)`, `GitLab Wiki Fetcher`, `Multi-Source Indexing Pipeline`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `reload_retrieval_state()` connect `Indexing Run Logging & Reload` to `Chat API & Model Lifecycle`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `_run()` connect `Indexing Run Logging & Reload` to `Multi-Source Indexing Pipeline`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `_run_pipeline()` (e.g. with `log_info()` and `log_warn()`) actually correct?**
  _`_run_pipeline()` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `run_all_sources_pipeline()` (e.g. with `fetch_repo_documents()` and `log_info()`) actually correct?**
  _`run_all_sources_pipeline()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `build_abbreviations_from_docstore()` (e.g. with `log_info()` and `log_warn()`) actually correct?**
  _`build_abbreviations_from_docstore()` has 3 INFERRED edges - model-reasoned connections that need verification._