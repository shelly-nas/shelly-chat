// Answering a question: the steps the server used to do, now in the browser.
//
//   1. expand abbreviations          NAS     POST /api/expand
//   2. embed the expanded question   Ollama  /api/embed (model of the index)
//   3. search + auto-merge           NAS     POST /api/retrieve (in the conversation's index)
//   4. stream the answer             Ollama  /api/chat
//
// host/rag.py is the same pipeline in Python, for the evaluation.
import { api } from "./api";
import { chatStream, embed, type ChatStats, type ChatTurn } from "./ollama";
import type { ChatMessage, ExpansionSource, MessageTimings, ServerConfig, SourceContext } from "./types";

export type Stage = "expanding" | "embedding" | "retrieving" | "generating";

export const STAGE_LABEL: Record<Stage, string> = {
  expanding: "Afkortingen opzoeken…",
  embedding: "Vraag omzetten met Ollama…",
  retrieving: "Bronnen zoeken op de NAS…",
  generating: "Antwoord schrijven…",
};

export function buildContextString(contexts: SourceContext[]): string {
  return contexts
    // The section path ("Contract X › Artikel 4") tells the model where a fragment belongs.
    .map((c, i) => `[${i + 1}] ${c.file_path}${c.section_context ? ` › ${c.section_context}` : ""} (page ${c.page_number})\n${c.content}`)
    .join("\n\n");
}

export function buildQaPrompt(contexts: SourceContext[], query: string): string {
  const sources = contexts.length ? buildContextString(contexts) : "(geen relevante bronnen gevonden)";
  return `BRONNEN:\n${sources}\n\nVRAAG: ${query}\n\nANTWOORD:`;
}

/** System prompt, the recent history and the question with its sources. */
export function buildMessages(
  config: Pick<ServerConfig, "system_prompt" | "history_max_turns">,
  history: ChatMessage[],
  contexts: SourceContext[],
  query: string,
  today: string = new Date().toISOString().slice(0, 10),
): ChatTurn[] {
  const turns: ChatTurn[] = history
    .filter((m) => m.content)
    .map((m) => ({
      role: m.role,
      // The model saw the expanded question; keep showing it that.
      content: m.role === "user" ? m.effective_query || m.content : m.content,
    }));
  return [
    { role: "system", content: config.system_prompt.replaceAll("{today}", today) },
    ...turns.slice(-config.history_max_turns * 2),
    { role: "user", content: buildQaPrompt(contexts, query) },
  ];
}

export interface AskOptions {
  question: string;
  /** The conversation's index: abbreviations and sources come only from it. null: none. */
  indexId: number | null;
  history: ChatMessage[];
  config: ServerConfig;
  ollamaUrl: string;
  llmModel: string;
  expandQuery: boolean;
  unloadModels: boolean;
  /** Let the model think before it answers; false is faster and keeps the answer short. */
  think: boolean;
  signal?: AbortSignal;
  onStage: (stage: Stage) => void;
  onExpansions: (query: string, expansions: ExpansionSource[]) => void;
  onSources: (sources: SourceContext[]) => void;
  onToken: (token: string) => void;
  /** Why the answer comes without sources although there is an index (search unavailable). */
  onNotice?: (notice: string) => void;
}

export interface AskResult {
  effectiveQuery: string;
  expansions: ExpansionSource[];
  sources: SourceContext[];
  answer: string;
  durationMs: number;
  timings: MessageTimings;
}

/** Search the index: expand, embed, retrieve. Throws when any step is unavailable. */
async function search(o: AskOptions, indexId: number, embedModel: string) {
  let query = o.question;
  let expansions: ExpansionSource[] = [];
  if (o.expandQuery) {
    o.onStage("expanding");
    ({ query, expansions } = await api.expand(o.question, indexId, o.signal));
    o.onExpansions(query, expansions);
  }
  o.onStage("embedding");
  // Models like Qwen3-Embedding search better with an instruction before the question.
  const embedding = await embed(o.ollamaUrl, embedModel, (o.config.query_prefix ?? "") + query, {
    unload: o.unloadModels,
    signal: o.signal,
  });
  o.onStage("retrieving");
  // The text goes along for the keyword half of hybrid search.
  const { contexts } = await api.retrieve(embedding, embedModel, indexId, query, o.signal);
  return { query, expansions, contexts };
}

export async function ask(o: AskOptions): Promise<AskResult> {
  // The index is a help, not a requirement: without one, or when searching
  // it fails, the model still answers, without sources ("Buiten de bronnen").
  let query = o.question;
  let expansions: ExpansionSource[] = [];
  let contexts: SourceContext[] = [];
  let searched = false;
  const searchStart = performance.now();
  if (o.indexId !== null) {
    if (!o.config.embed_model) {
      o.onNotice?.("Er is nog niets geïndexeerd, dus dit antwoord komt zonder bronnen.");
    } else {
      try {
        ({ query, expansions, contexts } = await search(o, o.indexId, o.config.embed_model));
        searched = true;
      } catch (err) {
        if (o.signal?.aborted) throw err;
        query = o.question;
        expansions = [];
        if (o.expandQuery) o.onExpansions(query, expansions);
        o.onNotice?.(`Zoeken in de index lukte niet (${(err as Error).message}), dus dit antwoord komt zonder bronnen.`);
      }
    }
  }
  o.onSources(contexts);
  const timings: MessageTimings = o.indexId !== null ? { search_ms: Math.round(performance.now() - searchStart) } : {};

  // Nothing relevant found: unless the model may answer from general knowledge
  // (marked as such by the system prompt), give the fixed no-answer text.
  if (searched && contexts.length === 0 && !o.config.answer_without_sources) {
    o.onToken(o.config.no_answer_response);
    return {
      effectiveQuery: query,
      expansions,
      sources: [],
      answer: o.config.no_answer_response,
      durationMs: 0,
      timings,
    };
  }

  o.onStage("generating");
  const start = performance.now();
  let answer = "";
  const messages = buildMessages(o.config, o.history, contexts, query);
  let stats: ChatStats | null = null;
  // The language model stays loaded between questions (LLM_KEEP_ALIVE); only
  // the embedding model is unloaded right away when unloadModels is on.
  for await (const token of chatStream(o.ollamaUrl, o.llmModel, messages, {
    options: o.config.llm_options,
    think: o.think,
    signal: o.signal,
    onStats: (s) => (stats = s),
  })) {
    answer += token;
    o.onToken(token);
  }
  return {
    effectiveQuery: query,
    expansions,
    sources: contexts,
    answer,
    durationMs: Math.round(performance.now() - start),
    timings: withStats(timings, stats),
  };
}

function withStats(timings: MessageTimings, stats: ChatStats | null): MessageTimings {
  if (!stats) return timings;
  return {
    ...timings,
    load_ms: stats.loadMs,
    prompt_tokens: stats.promptTokens,
    prompt_ms: stats.promptMs,
    output_tokens: stats.outputTokens,
    output_ms: stats.outputMs,
  };
}
