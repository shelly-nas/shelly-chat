-- Schema of a fresh shelly-chat database.
--
-- Before 1.0.0 the schema changes here directly (docker compose down -v gives a
-- clean start). From 1.0.0 on, every change is also a migration in
-- server/migrations/ - this file only runs on an empty data volume.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── Index ────────────────────────────────────────────────────────────────────
-- Filled by the indexer on the Ollama machine (host/indexing) through the
-- /api/index endpoints. The NAS itself never computes an embedding.

-- The configuration the index was built with. One row at most. When the
-- indexer runs with a different embedding model or chunk size it resets the
-- index, because vectors of two models can not be compared.
CREATE TABLE IF NOT EXISTS index_meta (
    id                   boolean PRIMARY KEY DEFAULT true CHECK (id),
    embed_model          text        NOT NULL,
    embed_dimensions     integer     NOT NULL,
    parent_chunk_size    integer     NOT NULL,
    child_chunk_size     integer     NOT NULL,
    parent_chunk_overlap integer     NOT NULL,
    updated_at           timestamptz NOT NULL DEFAULT now()
);

-- Named indexes ("Mijn BV", "Handboek"): what a conversation searches. Each
-- has its own sources and ignore patterns; the embedding model and chunk
-- configuration in index_meta are shared by all of them.
CREATE TABLE IF NOT EXISTS indexes (
    id              bigserial   PRIMARY KEY,
    name            text        NOT NULL UNIQUE,
    -- gitignore syntax, one pattern per line, matched against paths relative
    -- to the documents folder. Stored here; no .gitignore file is written.
    ignore_patterns text        NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Folders (recursively) or single files in an index, as paths relative to the
-- documents folder on the NAS (DOCUMENTS_DIR, / on acc and prod). '' is the
-- whole folder, refused when that is the whole NAS.
CREATE TABLE IF NOT EXISTS index_sources (
    id         bigserial   PRIMARY KEY,
    index_id   bigint      NOT NULL REFERENCES indexes (id) ON DELETE CASCADE,
    path       text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (index_id, path)
);

-- One row per indexed file; file_path is relative to the documents folder.
-- content_hash drives incremental indexing: an unchanged hash is skipped.
CREATE TABLE IF NOT EXISTS documents (
    id           bigserial PRIMARY KEY,
    file_path    text        NOT NULL UNIQUE,
    file_name    text        NOT NULL DEFAULT '',
    source_url   text        NOT NULL DEFAULT '',
    content_hash text        NOT NULL,
    content      text        NOT NULL DEFAULT '',
    metadata     jsonb       NOT NULL DEFAULT '{}',
    indexed_at   timestamptz NOT NULL DEFAULT now()
);

-- Which documents belong to which index. A file in two indexes is split and
-- embedded once; a document in no index any more is removed.
CREATE TABLE IF NOT EXISTS index_documents (
    index_id    bigint NOT NULL REFERENCES indexes (id) ON DELETE CASCADE,
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    PRIMARY KEY (index_id, document_id)
);
CREATE INDEX IF NOT EXISTS index_documents_document_id_idx ON index_documents (document_id);

-- Hierarchical chunks: large parent chunks and the small leaf chunks inside
-- them. Only leaves carry an embedding; a parent is returned instead of its
-- leaves when enough of them match (auto-merging retrieval).
--
-- The vector column has no fixed dimension, so a different embedding model
-- needs no schema change. The price is that pgvector can not build an
-- HNSW/IVFFlat index on it (and qwen3-embedding's 4096 dimensions exceed the
-- 2000 those indexes support anyway): search is an exact scan, which is fast
-- enough for tens of thousands of chunks.
CREATE TABLE IF NOT EXISTS chunks (
    id          text    PRIMARY KEY,
    document_id bigint  NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    -- Deferred, so a document's chunks can be inserted in any order.
    parent_id   text    REFERENCES chunks (id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    is_leaf     boolean NOT NULL,
    position    integer NOT NULL,
    content     text    NOT NULL,
    metadata    jsonb   NOT NULL DEFAULT '{}',
    embedding   vector
);
CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id);
CREATE INDEX IF NOT EXISTS chunks_parent_id_idx ON chunks (parent_id);

-- Abbreviation definitions found in the documents ("VI (Versleutelde
-- Identiteit)"), used to expand abbreviations in a question before it is
-- embedded. Extracted by the server when a document is stored.
CREATE TABLE IF NOT EXISTS abbreviations (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    abbrev      text   NOT NULL,
    term        text   NOT NULL,
    source_url  text   NOT NULL DEFAULT '',
    file_name   text   NOT NULL DEFAULT '',
    snippet     text   NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS abbreviations_abbrev_idx ON abbreviations (upper(abbrev));
CREATE INDEX IF NOT EXISTS abbreviations_document_id_idx ON abbreviations (document_id);

-- ── Conversations ────────────────────────────────────────────────────────────
-- Saved by the browser once an answer is complete. The answer itself is
-- generated on the user's own machine; the NAS only keeps the history.

CREATE TABLE IF NOT EXISTS conversations (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    title      text        NOT NULL DEFAULT 'Nieuw gesprek',
    -- Chosen when the conversation starts and fixed from then on. NULL once
    -- the index is deleted: the conversation stays readable.
    index_id   bigint      REFERENCES indexes (id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversations_updated_at_idx ON conversations (updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role            text        NOT NULL CHECK (role IN ('user', 'assistant')),
    content         text        NOT NULL,
    -- User messages: the question after abbreviation expansion, which is what
    -- the model saw and what later turns send back as history.
    effective_query text,
    expansions      jsonb       NOT NULL DEFAULT '[]',
    -- Assistant messages: the sources the answer was based on.
    sources         jsonb       NOT NULL DEFAULT '[]',
    model           text,
    duration_ms     integer,
    -- Assistant messages: where the time went (search, model load, reading the
    -- prompt, writing), as measured by the browser and reported by Ollama.
    timings         jsonb,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS messages_conversation_id_idx ON messages (conversation_id, created_at);

-- ── Settings ─────────────────────────────────────────────────────────────────
-- Shared settings changed in the app. A missing key means the default from
-- the environment (e.g. LLM_SYSTEM_PROMPT). Only the current value is kept.
CREATE TABLE IF NOT EXISTS app_settings (
    key        text        PRIMARY KEY,
    value      text        NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
