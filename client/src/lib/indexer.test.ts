import { describe, expect, it } from "vitest";

import { resetReason } from "./indexer";

describe("resetReason", () => {
  const chunks = { parent_chunk_size: 1500, child_chunk_size: 375, parent_chunk_overlap: 300 };
  const meta = { ...chunks, embed_model: "qwen3-embedding:latest", embed_dimensions: 4096, updated_at: "" };

  it("needs no reset for a fresh index or the same configuration", () => {
    expect(resetReason(null, chunks, "qwen3-embedding:latest")).toBeNull();
    expect(resetReason(meta, chunks, "qwen3-embedding:latest", 4096)).toBeNull();
  });

  it("resets for another model, dimension or chunk size", () => {
    expect(resetReason(meta, chunks, "nomic-embed-text")).toContain("ander embeddingmodel");
    expect(resetReason(meta, chunks, "qwen3-embedding:latest", 1024)).toContain("andere dimensie");
    expect(resetReason(meta, { ...chunks, parent_chunk_size: 1000 }, "qwen3-embedding:latest")).toContain("parent_chunk_size");
  });
});
