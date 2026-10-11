import { describe, expect, it, vi } from "vitest";

import { randomId } from "./id";

describe("randomId", () => {
  it("is a v4 UUID without crypto.randomUUID (plain http)", () => {
    vi.stubGlobal("crypto", { getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto) });
    const id = randomId();
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(randomId()).not.toBe(id);
    vi.unstubAllGlobals();
  });
});
