// Answering a question: the steps the server used to do, now in the browser.
//
//   1. expand abbreviations          NAS     POST /api/expand
//   2. embed the expanded question   Ollama  /api/embed (model of the index)
//   3. search + auto-merge           NAS     POST /api/retrieve (in the conversation's index)
//   4. stream the answer             Ollama  /api/chat
//
// host/rag.py is the same pipeline in Python, for the evaluation.
import { api } from "./api";
import { chatStream, embed, type ChatTurn } from "./ollama";
import type { ChatMessage, ExpansionSource, ServerConfig, SourceContext } from "./types";

export type Stage = "expanding" | "embedding" | "retrieving" | "generating";

export const STAGE_LABEL: Record<Stage, string> = {
  expanding: "Afkortingen opzoeken…",
  embedding: "Vraag omzetten met Ollama…",
  retrieving: "Bronnen zoeken op de NAS…",
  generating: "Antwoord schrijven…",
};

export function buildContextString(contexts: SourceContext[]): string {
  return contexts
    .map((c, i) => `[${i + 1}] ${c.file_path} (page ${c.page_number})\n${c.content}`)
    .join("\n\n");
}

export function buildQaPrompt(contexts: SourceContext[], query: string): string {
  return `SOURCES:\n${buildContextString(contexts)}\n\nQUESTION: ${query}\n\nANSWER:`;
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
  /** The conversation's index: abbreviations and sources come only from it. */
  indexId: number;
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
}

export interface AskResult {
  effectiveQuery: string;
  expansions: ExpansionSource[];
  sources: SourceContext[];
  answer: string;
  durationMs: number;
}

export async function ask(o: AskOptions): Promise<AskResult> {
  if (!o.config.embed_model) {
    throw new Error("Er is nog niets geïndexeerd. Open Index in de zijbalk om documenten te indexeren.");
  }

  let query = o.question;
  let expansions: ExpansionSource[] = [];
  if (o.expandQuery) {
    o.onStage("expanding");
    ({ query, expansions } = await api.expand(o.question, o.indexId, o.signal));
    o.onExpansions(query, expansions);
  }

  o.onStage("embedding");
  const embedding = await embed(o.ollamaUrl, o.config.embed_model, query, {
    unload: o.unloadModels,
    signal: o.signal,
  });

  o.onStage("retrieving");
  const { contexts } = await api.retrieve(embedding, o.config.embed_model, o.indexId, o.signal);
  o.onSources(contexts);

  // No sources: refuse rather than let the model make something up.
  if (contexts.length === 0) {
    o.onToken(o.config.no_answer_response);
    return {
      effectiveQuery: query,
      expansions,
      sources: [],
      answer: o.config.no_answer_response,
      durationMs: 0,
    };
  }

  o.onStage("generating");
  const start = performance.now();
  let answer = "";
  const messages = buildMessages(o.config, o.history, contexts, query);
  for await (const token of chatStream(o.ollamaUrl, o.llmModel, messages, {
    options: o.config.llm_options,
    unload: o.unloadModels,
    think: o.think,
    signal: o.signal,
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
  };
}
