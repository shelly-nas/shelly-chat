// Where the time of one answer went, in words.
import type { MessageTimings } from "./types";

export function formatDuration(ms: number): string {
  return ms < 10_000 ? `${(ms / 1000).toFixed(1).replace(".", ",")} s` : `${Math.round(ms / 1000)} s`;
}

/** "zoeken 0,8 s · model laden 4,2 s · inlezen 3,1 s (12.345 tokens) · schrijven 6,1 s (18 tokens/s)" */
export function describeTimings(t: MessageTimings): string {
  const parts: string[] = [];
  if (t.search_ms !== undefined) parts.push(`zoeken ${formatDuration(t.search_ms)}`);
  // Under half a second the model was still loaded: not worth a mention.
  if (t.load_ms !== undefined && t.load_ms >= 500) parts.push(`model laden ${formatDuration(t.load_ms)}`);
  if (t.prompt_ms !== undefined)
    parts.push(`inlezen ${formatDuration(t.prompt_ms)} (${(t.prompt_tokens ?? 0).toLocaleString("nl-NL")} tokens)`);
  if (t.output_ms !== undefined && t.output_tokens) {
    const rate = t.output_ms > 0 ? Math.round((t.output_tokens / t.output_ms) * 1000) : 0;
    parts.push(`schrijven ${formatDuration(t.output_ms)} (${rate} tokens/s)`);
  }
  return parts.join(" · ");
}
