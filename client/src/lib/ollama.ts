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

export async function* chatStream(
  ollamaUrl: string,
  model: string,
  messages: ChatTurn[],
  opts: { options?: Record<string, number>; unload: boolean; think?: boolean; signal?: AbortSignal },
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
      ...(opts.unload ? { keep_alive: 0 } : {}),
    }),
    signal: opts.signal,
  });
  for await (const chunk of readNdjson(res.body!)) {
    if (chunk.error) throw new OllamaError(chunk.error, "other");
    const token = chunk.message?.content;
    if (token) yield token;
  }
}
