export interface SourceContext {
  content: string;
  file_path: string;
  source_url?: string;
  page_number: number | string;
  start_line: number;
  end_line: number;
  section_context: string;
  similarity: number;
  source_num: number;
  chunk_type?: "parent" | "child";
}

export interface ExpansionSource {
  abbrev: string;
  term: string;
  source_url: string;
  file_name: string;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  effective_query?: string | null;
  expansions?: ExpansionSource[];
  sources?: SourceContext[];
  model?: string | null;
  duration_ms?: number | null;
  created_at?: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  /** Fixed when the conversation starts; null once the index is deleted. */
  index_id: number | null;
  index_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface Conversation extends ConversationSummary {
  messages: ChatMessage[];
}

export interface ServerConfig {
  llm_model: string;
  system_prompt: string;
  no_answer_response: string;
  /** Ask the model even without a relevant source; else no_answer_response. */
  answer_without_sources: boolean;
  history_max_turns: number;
  query_max_length: number;
  llm_options: Record<string, number>;
  embed_model: string | null;
}

export interface IndexStatus {
  meta: {
    embed_model: string;
    embed_dimensions: number;
    parent_chunk_size: number;
    child_chunk_size: number;
    parent_chunk_overlap: number;
    updated_at: string;
  } | null;
  documents: number;
  chunks: number;
  abbreviations: number;
  last_indexed_at: string | null;
  indexes: number;
}

export interface ChunkConfig {
  parent_chunk_size: number;
  child_chunk_size: number;
  parent_chunk_overlap: number;
}

/** A folder (indexed recursively) or a single file, relative to the documents folder. */
export interface IndexSource {
  id: number;
  path: string;
  created_at: string;
  exists: boolean;
  /** Documents in it now, after the index's ignore patterns. */
  documents: number;
}

/** A named index ("Mijn BV"): what a conversation searches. */
export interface DocIndex {
  id: number;
  name: string;
  /** gitignore syntax, against paths relative to the documents folder. */
  ignore_patterns: string;
  sources: IndexSource[];
  /** Indexed documents in it. */
  documents: number;
  last_indexed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Shared by all indexes. */
export interface IndexSettings {
  meta: IndexStatus["meta"];
  chunk_config: ChunkConfig;
  /** The model the next run embeds with (Instellingen → Indexeren); meta has the store's. */
  embed_model: string;
  /** The documents folder as the NAS sees it, e.g. /volume1/docker/shelly-chat/documents. */
  documents_dir: string;
  documents_root_exists: boolean;
}

/** Settings that apply to everyone, kept on the NAS (GET/PUT /api/settings). */
export interface SharedValues {
  system_prompt: string;
  no_answer_response: string;
  llm_temperature: number;
  llm_top_p: number;
  llm_top_k: number;
  llm_num_ctx: number;
  llm_max_tokens: number;
  retrieval_top_k: number;
  context_top_n: number;
  automerge_threshold: number;
  min_similarity: number;
  answer_without_sources: boolean;
  history_max_turns: number;
  query_max_length: number;
  embed_model: string;
  parent_chunk_size: number;
  child_chunk_size: number;
  parent_chunk_overlap: number;
  max_file_mb: number;
}

export interface SharedSettings {
  values: SharedValues;
  /** From the environment on the NAS; what "Standaard" goes back to. */
  defaults: SharedValues;
  /** Keys that differ from their default. */
  changed: (keyof SharedValues)[];
}

export interface BrowseResult {
  path: string;
  folders: string[];
  documents: string[];
}

export interface PreparedNode {
  id: string;
  parent_id: string | null;
  is_leaf: boolean;
  position: number;
  content: string;
  metadata: Record<string, unknown>;
  embed_text: string | null;
}

export interface PrepareResult {
  file_path: string;
  status: "new" | "changed" | "unchanged" | "empty";
  content_hash?: string;
  document?: {
    file_path: string;
    file_name: string;
    source_url: string;
    content_hash: string;
    content: string;
    metadata: Record<string, unknown>;
    nodes: PreparedNode[];
  };
}
