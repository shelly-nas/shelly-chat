// Ollama on the user's own machine, called straight from the browser.
//
// This is the point of the architecture: the NAS serves the app and the data,
// but the models run where the user is. Ollama has to allow the app's origin
// (OLLAMA_ORIGINS, see README.md), or the browser blocks these requests.

export class OllamaError extends Error {
  constructor(
    message: string,
    public kind: "unreachable" | "model" | "other",
  ) {
    super(message);
  }
}

export interface OllamaModel {
  name: string;
  model: string;
  size: number;
}

export interface ChatTurn {
  role: "system" | "user" | "assistant";
  content: string;
}

function base(url: string): string {
  return url.replace(/\/+$/, "");
}

async function call(url: string, init: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    // A network error and a CORS refusal look the same from here.
    throw new OllamaError(`Ollama is niet bereikbaar op ${new URL(url).origin}.`, "unreachable");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).error ?? detail;
    } catch {
      // keep statusText
    }
    const kind = res.status === 404 ? "model" : "other";
    throw new OllamaError(detail, kind);
  }
  return res;
}

export async function listModels(ollamaUrl: string, signal?: AbortSignal): Promise<OllamaModel[]> {
  const res = await call(`${base(ollamaUrl)}/api/tags`, { signal });
  return (await res.json()).models ?? [];
}

/** Whether `wanted` is installed; "gemma4" matches "gemma4:latest". */
export function hasModel(models: OllamaModel[], wanted: string): boolean {
  const normalize = (n: string) => (n.includes(":") ? n : `${n}:latest`);
  return models.some((m) => normalize(m.name) === normalize(wanted));
}

export async function embed(
  ollamaUrl: string,
  model: string,
  input: string,
  opts: { unload: boolean; signal?: AbortSignal },
): Promise<number[]> {
  const res = await call(`${base(ollamaUrl)}/api/embed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // keep_alive 0 frees the embedding model before the LLM loads, so both
    // fit in limited (V)RAM one after the other.
    body: JSON.stringify({ model, input: [input], ...(opts.unload ? { keep_alive: 0 } : {}) }),
    signal: opts.signal,
  });
  return (await res.json()).embeddings[0];
}

export async function embedMany(
  ollamaUrl: string,
  model: string,
  inputs: string[],
  opts: { batchSize?: number; signal?: AbortSignal } = {},
): Promise<number[][]> {
  const size = opts.batchSize ?? 16;
  const vectors: number[][] = [];
  for (let i = 0; i < inputs.length; i += size) {
    const res = await call(`${base(ollamaUrl)}/api/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, input: inputs.slice(i, i + size) }),
      signal: opts.signal,
    });
    vectors.push(...(await res.json()).embeddings);
  }
  return vectors;
}

/** Have a vision model describe one image (base64 PNG); the whole answer at once. */
export async function describeImage(
  ollamaUrl: string,
  model: string,
  prompt: string,
  image: string,
  signal?: AbortSignal,
): Promise<string> {
  const res = await call(`${base(ollamaUrl)}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content: prompt, images: [image] }],
      stream: false,
      think: false,
      options: { temperature: 0 },
    }),
    signal,
  });
  return ((await res.json()).message?.content ?? "").trim();
}

/** Free a model's memory now instead of after Ollama's keep-alive. */
export async function unload(ollamaUrl: string, model: string): Promise<void> {
  await call(`${base(ollamaUrl)}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, prompt: "", keep_alive: 0 }),
  });
}

/** Ollama streams newline-delimited JSON; yield each complete object. */
export async function* readNdjson(body: ReadableStream<Uint8Array>): AsyncGenerator<any> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline: number;
    while ((newline = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) yield JSON.parse(line);
    }
  }
  if (buffer.trim()) yield JSON.parse(buffer);
}

/** What Ollama reports at the end of an answer, in milliseconds and tokens. */
export interface ChatStats {
  loadMs: number;
  promptTokens: number;
  promptMs: number;
  outputTokens: number;
  outputMs: number;
}

/**
 * How long the language model stays loaded after an answer. Reloading it costs
 * seconds per question, and the cached prompt goes with it; a follow-up
 * question within this time starts right away.
 */
export const LLM_KEEP_ALIVE = "10m";

export async function* chatStream(
  ollamaUrl: string,
  model: string,
  messages: ChatTurn[],
  opts: { options?: Record<string, number>; think?: boolean; signal?: AbortSignal; onStats?: (s: ChatStats) => void },
): AsyncGenerator<string> {
  const res = await call(`${base(ollamaUrl)}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages,
      stream: true,
      options: opts.options,
      // false switches thinking off for every model that thinks (Qwen3,
      // gpt-oss, Gemma); models that do not think ignore it.
      ...(opts.think === undefined ? {} : { think: opts.think }),
      keep_alive: LLM_KEEP_ALIVE,
    }),
    signal: opts.signal,
  });
  for await (const chunk of readNdjson(res.body!)) {
    if (chunk.error) throw new OllamaError(chunk.error, "other");
    const token = chunk.message?.content;
    if (token) yield token;
    if (chunk.done && opts.onStats) {
      const ms = (ns: number | undefined) => Math.round((ns ?? 0) / 1e6);
      opts.onStats({
        loadMs: ms(chunk.load_duration),
        promptTokens: chunk.prompt_eval_count ?? 0,
        promptMs: ms(chunk.prompt_eval_duration),
        outputTokens: chunk.eval_count ?? 0,
        outputMs: ms(chunk.eval_duration),
      });
    }
  }
}
