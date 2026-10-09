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
}
