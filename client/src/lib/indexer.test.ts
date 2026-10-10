import { describe, expect, it } from "vitest";

import { extensionOf, parseRepoUrl, parseWikiUrl } from "./gitlab";
import { resetReason } from "./indexer";

describe("GitLab URLs", () => {
  it("reads wiki URLs with or without a page", () => {
    expect(parseWikiUrl("https://gitlab.example.com/team/handbook/-/wikis/home")).toEqual({
      base: "https://gitlab.example.com",
      project: "team/handbook",
    });
    expect(parseWikiUrl("https://gitlab.example.com/a/b/c/-/wikis/").project).toBe("a/b/c");
  });

  it("reads a branch and folder from tree URLs", () => {
    expect(parseRepoUrl("https://gitlab.example.com/team/app/-/tree/main/docs?ref_type=heads")).toEqual({
      base: "https://gitlab.example.com",
      project: "team/app",
      branch: "main",
      path: "docs",
    });
    expect(parseRepoUrl("https://gitlab.example.com/team/app")).toMatchObject({ project: "team/app", branch: undefined });
  });

  it("finds extensions", () => {
    expect(extensionOf("docs/Handleiding.PDF")).toBe(".pdf");
    expect(extensionOf("Makefile")).toBe("");
  });
});

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
