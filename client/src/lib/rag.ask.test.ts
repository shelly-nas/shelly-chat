import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ServerConfig } from "./types";

vi.mock("./api", () => ({
  api: { expand: vi.fn(), retrieve: vi.fn() },
}));
vi.mock("./ollama", () => ({
  embed: vi.fn(),
  chatStream: vi.fn(async function* () {
    yield "Buiten de bronnen: ";
    yield "een antwoord.";
  }),
}));

const { api } = await import("./api");
const ollama = await import("./ollama");
const { ask } = await import("./rag");

const config = {
  llm_model: "m",
  system_prompt: "s",
  no_answer_response: "niets",
  answer_without_sources: true,
  history_max_turns: 10,
  query_max_length: 4000,
  llm_options: {},
  embed_model: "e",
} as unknown as ServerConfig;

const options = (overrides = {}) => ({
  question: "Wat is X?",
  indexId: 1 as number | null,
  history: [],
  config,
  ollamaUrl: "http://localhost:11434",
  llmModel: "m",
  expandQuery: true,
  unloadModels: false,
  think: false,
  onStage: vi.fn(),
  onExpansions: vi.fn(),
  onSources: vi.fn(),
  onToken: vi.fn(),
  onNotice: vi.fn(),
  ...overrides,
});

describe("ask without a vector database", () => {
  beforeEach(() => vi.clearAllMocks());

  it("answers without an index, without searching", async () => {
    const o = options({ indexId: null });
    const result = await ask(o);
    expect(api.expand).not.toHaveBeenCalled();
    expect(ollama.embed).not.toHaveBeenCalled();
    expect(result.answer).toBe("Buiten de bronnen: een antwoord.");
    expect(result.sources).toEqual([]);
    expect(o.onNotice).not.toHaveBeenCalled();
  });

  it("answers when searching fails, and says why there are no sources", async () => {
    vi.mocked(api.expand).mockResolvedValue({ query: "Wat is X?", expansions: [] });
    vi.mocked(ollama.embed).mockRejectedValue(new Error("model qwen3-embedding not found"));
    const o = options();
    const result = await ask(o);
    expect(result.answer).toBe("Buiten de bronnen: een antwoord.");
    expect(o.onNotice).toHaveBeenCalledWith(expect.stringContaining("qwen3-embedding not found"));
  });

  it("answers when nothing is indexed yet", async () => {
    const o = options({ config: { ...config, embed_model: null } });
    const result = await ask(o);
    expect(ollama.embed).not.toHaveBeenCalled();
    expect(result.answer).toBe("Buiten de bronnen: een antwoord.");
    expect(o.onNotice).toHaveBeenCalledWith(expect.stringContaining("nog niets geïndexeerd"));
  });
});
