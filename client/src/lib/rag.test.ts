import { describe, expect, it } from "vitest";

import { hasModel, readNdjson } from "./ollama";
import { buildMessages, buildQaPrompt } from "./rag";
import type { ChatMessage, SourceContext } from "./types";

const source = (n: number, content: string): SourceContext => ({
  content,
  file_path: `wiki/${n}.md`,
  page_number: 1,
  start_line: 1,
  end_line: 1,
  section_context: "",
  similarity: 0.9,
  source_num: n,
});

describe("buildMessages", () => {
  it("puts the system prompt first, the history after it and the question with sources last", () => {
    const history: ChatMessage[] = [
      { id: "1", role: "user", content: "Wat is VI?", effective_query: "Wat is VI (Versleutelde Identiteit)?" },
      { id: "2", role: "assistant", content: "Een identiteit." },
    ];
    const messages = buildMessages(
      { system_prompt: "Vandaag is {today}.", history_max_turns: 10 },
      history,
      [source(1, "alpha")],
      "En nu?",
      "2026-10-09",
    );
    expect(messages.map((m) => m.role)).toEqual(["system", "user", "assistant", "user"]);
    expect(messages[0].content).toBe("Vandaag is 2026-10-09.");
    // History sends the expanded question, as the model saw it then.
    expect(messages[1].content).toBe("Wat is VI (Versleutelde Identiteit)?");
    expect(messages[3].content).toBe(buildQaPrompt([source(1, "alpha")], "En nu?"));
    expect(messages[3].content).toContain("[1] wiki/1.md (page 1)\nalpha");
  });

  it("keeps only the last turns", () => {
    const history: ChatMessage[] = Array.from({ length: 10 }, (_, i) => ({
      id: String(i),
      role: i % 2 ? "assistant" : "user",
      content: `m${i}`,
    }));
    const messages = buildMessages({ system_prompt: "s", history_max_turns: 2 }, history, [], "q");
    expect(messages.slice(1, -1).map((m) => m.content)).toEqual(["m6", "m7", "m8", "m9"]);
  });
});

describe("readNdjson", () => {
  it("joins objects split across chunks", async () => {
    const encoder = new TextEncoder();
    const parts = ['{"message":{"content":"Hal', 'lo"}}\n{"message":{"content":" daar"}}\n{"done":true}'];
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        parts.forEach((p) => controller.enqueue(encoder.encode(p)));
        controller.close();
      },
    });
    const out = [];
    for await (const obj of readNdjson(body)) out.push(obj);
    expect(out).toEqual([
      { message: { content: "Hallo" } },
      { message: { content: " daar" } },
      { done: true },
    ]);
  });
});

describe("hasModel", () => {
  it("treats a missing tag as latest", () => {
    const models = [{ name: "gemma4:latest", model: "gemma4:latest", size: 1 }];
    expect(hasModel(models, "gemma4")).toBe(true);
    expect(hasModel(models, "gemma4:latest")).toBe(true);
    expect(hasModel(models, "qwen3-embedding")).toBe(false);
  });
});
