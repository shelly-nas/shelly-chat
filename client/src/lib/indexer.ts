// Indexing one named index from the browser: NAS (read + split) → Ollama (embed) → NAS (store).
//
//   1. Embedding model and dimension, shared by all indexes. A different model
//      or chunk size than the store was built with means starting over: those
//      vectors do not mix, so every index has to be indexed again.
//   2. The NAS lists the documents in the index's sources, minus its ignore
//      patterns, so the total is known.
//   3. Per document: POST /api/index/prepare (the NAS reads, extracts, hashes
//      and splits; a document already embedded - perhaps for another index -
//      just joins this one), embed the leaf chunks with Ollama, PUT
//      /api/index/documents.
//   4. Prune: documents that left the index (deleted, ignored, source removed)
//      leave it - only when every source could be read, so a missing folder
//      never empties an index.
//
// host/indexing/indexer.py is the same run for the command line.
import { api } from "./api";
import { randomId } from "./id";
import { embedMany, unload } from "./ollama";
import type { ChunkConfig, IndexSettings } from "./types";

export type LogLevel = "info" | "success" | "warning" | "error";

export interface RunCounts {
  new: number;
  changed: number;
  unchanged: number;
  deleted: number;
  failed: number;
}

export interface RunProgress {
  /** listing: the NAS lists the index's documents; indexing: one by one; finishing: pruning. */
  phase: "listing" | "indexing" | "finishing";
  /** The index being worked on, and which of how many in this run. */
  index: string;
  indexNumber: number;
  indexCount: number;
  done: number;
  total: number;
  current: string | null;
  counts: RunCounts;
}

/** "1,2 s" */
const seconds = (ms: number) => `${(ms / 1000).toLocaleString("nl-NL", { maximumFractionDigits: 1 })} s`;

export interface RunOptions {
  ollamaUrl: string;
  embedModel: string;
  indexToken: string;
  /** Empty the whole store first (all indexes). */
  full: boolean;
  signal: AbortSignal;
  log: (level: LogLevel, message: string) => void;
  progress: (p: RunProgress) => void;
}

/** Why the store must be rebuilt for this model, or null when it need not be. */
export function resetReason(
  meta: IndexSettings["meta"],
  chunks: ChunkConfig,
  embedModel: string,
  dimensions?: number,
): string | null {
  if (!meta) return null;
  if (meta.embed_model !== embedModel) return `ander embeddingmodel (${meta.embed_model} → ${embedModel})`;
  if (dimensions !== undefined && meta.embed_dimensions !== dimensions)
    return `andere dimensie (${meta.embed_dimensions} → ${dimensions})`;
  const changed = (Object.keys(chunks) as (keyof ChunkConfig)[]).filter((k) => meta[k] !== chunks[k]);
  return changed.length ? `andere chunkinstellingen (${changed.join(", ")})` : null;
}

const emptyCounts = (): RunCounts => ({ new: 0, changed: 0, unchanged: 0, deleted: 0, failed: 0 });

/** Step 1: make sure the store uses this model; resets it when needed. Returns whether it did. */
async function prepareStore(o: RunOptions): Promise<boolean> {
  const settings = await api.indexSettings();
  const sameModel = settings.meta?.embed_model === o.embedModel;
  let dimensions = sameModel ? settings.meta!.embed_dimensions : 0;
  if (!sameModel) {
    o.log("info", `${o.embedModel} laden om de dimensie te bepalen…`);
    dimensions = (await embedMany(o.ollamaUrl, o.embedModel, ["dimensie"], { signal: o.signal }))[0].length;
  }
  const reason = resetReason(settings.meta, settings.chunk_config, o.embedModel, dimensions);
  const reset = o.full || reason !== null;
  if (reason) o.log("warning", `Alle indexen worden opnieuw opgebouwd: ${reason}.`);
  else if (o.full) o.log("info", "Volledig opnieuw: alle geïndexeerde documenten worden eerst verwijderd.");
  await api.putIndexMeta(o.indexToken, { embed_model: o.embedModel, embed_dimensions: dimensions, reset });
  return reset;
}

/** Steps 2-4 for one index; `position` is [which, of how many] in this run. */
async function indexOne(
  o: RunOptions,
  indexId: number,
  name: string,
  counts: RunCounts,
  position: [number, number],
): Promise<void> {
  let total = 0;
  const report = (phase: RunProgress["phase"], current: string | null, done: number) =>
    o.progress({ phase, index: name, indexNumber: position[0], indexCount: position[1], done, total, current, counts: { ...counts } });

  report("listing", null, 0);
  let started = performance.now();
  const { files, missing } = await api.indexFiles(o.indexToken, indexId);
  total = files.length;
  for (const source of missing) o.log("error", `${name}: bron '${source || "."}' bestaat niet (meer) in de documentenmap; overgeslagen.`);
  o.log("info", `${name}: ${files.length} documenten gevonden in ${seconds(performance.now() - started)}.`);

  for (const [i, filePath] of files.entries()) {
    if (o.signal.aborted) throw new DOMException("Gestopt", "AbortError");
    report("indexing", filePath, i);
    try {
      started = performance.now();
      const prepared = await api.prepareDocument(o.indexToken, filePath, indexId, o.signal);
      const read = performance.now() - started;
      if (prepared.status === "unchanged" || prepared.status === "empty") {
        counts.unchanged++;
        // Unchanged still means the NAS read and hashed it; say so when that took long.
        if (read > 5000) o.log("info", `${filePath}: ongewijzigd, maar lezen duurde ${seconds(read)}.`);
        continue;
      }
      const doc = prepared.document!;
      const leaves = doc.nodes.filter((n) => n.is_leaf);
      started = performance.now();
      const vectors = await embedMany(o.ollamaUrl, o.embedModel, leaves.map((n) => n.embed_text!), {
        signal: o.signal,
      });
      const embedded = performance.now() - started;
      started = performance.now();
      const byId = new Map(leaves.map((n, j) => [n.id, vectors[j]]));
      const stored = await api.putDocument(
        o.indexToken,
        {
          ...doc,
          index_id: indexId,
          nodes: doc.nodes.map(({ embed_text: _, ...n }) => ({ ...n, embedding: byId.get(n.id) ?? null })),
        },
        o.signal,
      );
      counts[prepared.status]++;
      const extra = stored.abbreviations ? `, ${stored.abbreviations} afkortingen` : "";
      // Where the time goes: reading and splitting on the NAS, embedding with Ollama, storing on the NAS.
      const timing = `lezen ${seconds(read)} · embedden ${seconds(embedded)} · opslaan ${seconds(performance.now() - started)}`;
      o.log("success", `${filePath}: ${prepared.status === "new" ? "nieuw" : "gewijzigd"}, ${stored.chunks} chunks${extra} (${timing})`);
    } catch (err) {
      if (o.signal.aborted) throw err;
      counts.failed++;
      o.log("error", `${filePath}: ${(err as Error).message}`);
    }
  }
  report("finishing", null, files.length);

  if (missing.length) {
    o.log("warning", `${name}: niets uit de index gehaald, want niet elke bron kon worden gelezen.`);
    return;
  }
  started = performance.now();
  const pruned = await api.pruneIndex(o.indexToken, indexId, files);
  counts.deleted += pruned.removed;
  if (pruned.removed) o.log("info", `${name}: ${pruned.removed} documenten uit de index gehaald die er niet meer in horen.`);
  o.log("info", `${name}: klaar, opgeruimd in ${seconds(performance.now() - started)}.`);
  report("finishing", null, files.length);
}

/** How often a run renews its lock on the NAS; the NAS lets it go after 3 minutes without. */
const LEASE_RENEW_MS = 30_000;

/**
 * Index one or more indexes after each other; `full` empties the store once, first.
 * Only one run at a time, across tabs, computers and the CLI: the run holds a
 * lock on the NAS (PUT /api/index/run) and fails up front while another has it.
 */
export async function runIndexes(o: RunOptions, indexes: { id: number; name: string }[]): Promise<RunCounts> {
  const counts = emptyCounts();
  if (indexes.length === 0) throw new Error("Er is geen index om te indexeren.");
  const runId = randomId();
  const label = indexes.map((i) => i.name).join(", ");
  await api.leaseRun(o.indexToken, runId, label);
  const renew = setInterval(() => {
    api.leaseRun(o.indexToken, runId, label).catch((err) => o.log("warning", `Slot op de NAS verlengen mislukt: ${(err as Error).message}`));
  }, LEASE_RENEW_MS);
  try {
    await prepareStore(o);
    for (const [i, index] of indexes.entries()) {
      if (o.signal.aborted) throw new DOMException("Gestopt", "AbortError");
      await indexOne(o, index.id, index.name, counts, [i + 1, indexes.length]);
    }
  } finally {
    clearInterval(renew);
    api.endRun(o.indexToken, runId).catch(() => {});
    unload(o.ollamaUrl, o.embedModel).catch(() => {});
  }
  return counts;
}
