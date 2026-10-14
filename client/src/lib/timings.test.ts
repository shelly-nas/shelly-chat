import { describe, expect, it } from "vitest";

import { describeTimings } from "./timings";

describe("describeTimings", () => {
  it("says where the time went", () => {
    expect(
      describeTimings({ search_ms: 800, load_ms: 4200, prompt_tokens: 12345, prompt_ms: 3100, output_tokens: 110, output_ms: 6100 }),
    ).toBe("zoeken 0,8 s · model laden 4,2 s · inlezen 3,1 s (12.345 tokens) · schrijven 6,1 s (18 tokens/s)");
  });

  it("leaves out a model that was still loaded, and what was not measured", () => {
    expect(describeTimings({ load_ms: 120, prompt_tokens: 900, prompt_ms: 400, output_tokens: 50, output_ms: 2000 })).toBe(
      "inlezen 0,4 s (900 tokens) · schrijven 2,0 s (25 tokens/s)",
    );
    expect(describeTimings({})).toBe("");
  });
});
