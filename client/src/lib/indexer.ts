// One indexing run from the browser: GitLab → NAS (split) → Ollama (embed) → NAS (store).
//
//   1. Embedding model and dimension. A different model or chunk size than the
//      index was built with means starting over: those vectors do not mix.
//   2. List every source in GitLab first, so the total is known.
//   3. Per document: POST /api/index/prepare (the NAS extracts, hashes and
//      splits; unchanged documents stop here), embed the leaf chunks with
//      Ollama, PUT /api/index/documents.
//   4. Remove documents that are gone from GitLab - only when every source
//      could be read, so a VPN hiccup never empties the index.
//
// host/indexing/indexer.py is the same run for the command line.
import { api } from "./api";
import { listRepo, listWiki, type SourceItem } from "./gitlab";
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
  done: number;
  total: number;
  current: string | null;
  counts: RunCounts;
}

export interface RunOptions {
  ollamaUrl: string;
  embedModel: string;
  indexToken: string;
  gitlabToken: string;
  full: boolean;
  signal: AbortSignal;
  log: (level: LogLevel, message: string) => void;
  progress: (p: RunProgress) => void;
}

/** Why the index must be rebuilt for this model, or null when it need not be. */
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

export async function runIndex(o: RunOptions): Promise<RunCounts> {
  const counts: RunCounts = { new: 0, changed: 0, unchanged: 0, deleted: 0, failed: 0 };
  const settings = await api.indexSettings();
  if (settings.sources.length === 0) throw new Error("Voeg eerst een bron toe.");

  // 1. Model and dimension
  const sameModel = settings.meta?.embed_model === o.embedModel;
  let dimensions = sameModel ? settings.meta!.embed_dimensions : 0;
  if (!sameModel) {
    o.log("info", `${o.embedModel} laden om de dimensie te bepalen…`);
    dimensions = (await embedMany(o.ollamaUrl, o.embedModel, ["dimensie"], { signal: o.signal }))[0].length;
  }
  const reason = resetReason(settings.meta, settings.chunk_config, o.embedModel, dimensions);
  const reset = o.full || reason !== null;
  if (reason) o.log("warning", `De index wordt opnieuw opgebouwd: ${reason}.`);
  else if (o.full) o.log("info", "Volledig opnieuw: de index wordt eerst geleegd.");
  await api.putIndexMeta(o.indexToken, { embed_model: o.embedModel, embed_dimensions: dimensions, reset });
  const indexed = reset ? [] : await api.indexedDocuments(o.indexToken);

  // 2. List the sources
  const items: SourceItem[] = [];
  let allListed = true;
  for (const source of settings.sources) {
    try {
      const found = await (source.kind === "wiki" ? listWiki : listRepo)(source.url, o.gitlabToken, o.signal);
      o.log("info", `${source.url}: ${found.length} ${source.kind === "wiki" ? "pagina's" : "bestanden"}`);
      items.push(...found);
    } catch (err) {
      if (o.signal.aborted) throw err;
      allListed = false;
      o.log("error", `${source.url}: ${(err as Error).message} Deze bron wordt overgeslagen.`);
    }
  }

  const report = (current: string | null, done: number) =>
    o.progress({ done, total: items.length, current, counts: { ...counts } });
  report(null, 0);

  // 3. Prepare, embed and store each document
  const seen = new Set<string>();
  try {
    for (const [i, item] of items.entries()) {
      if (o.signal.aborted) throw new DOMException("Gestopt", "AbortError");
      seen.add(item.file_path);
      report(item.file_name, i);
      try {
        const content = await item.load(o.signal);
        const prepared = await api.prepareDocument(
          o.indexToken,
          { file_path: item.file_path, file_name: item.file_name, source_url: item.source_url, metadata: item.metadata, ...content },
          o.signal,
        );
        if (prepared.status === "unchanged" || prepared.status === "empty") {
          counts.unchanged++;
          continue;
        }
        const doc = prepared.document!;
        const leaves = doc.nodes.filter((n) => n.is_leaf);
        const vectors = await embedMany(o.ollamaUrl, o.embedModel, leaves.map((n) => n.embed_text!), {
          signal: o.signal,
        });
        const byId = new Map(leaves.map((n, j) => [n.id, vectors[j]]));
        const stored = await api.putDocument(
          o.indexToken,
          {
            ...doc,
            nodes: doc.nodes.map(({ embed_text: _, ...n }) => ({ ...n, embedding: byId.get(n.id) ?? null })),
          },
          o.signal,
        );
        counts[prepared.status]++;
        const extra = stored.abbreviations ? `, ${stored.abbreviations} afkortingen` : "";
        o.log("success", `${item.file_name}: ${prepared.status === "new" ? "nieuw" : "gewijzigd"}, ${stored.chunks} chunks${extra}`);
      } catch (err) {
        if (o.signal.aborted) throw err;
        counts.failed++;
        o.log("error", `${item.file_name}: ${(err as Error).message}`);
      }
    }
    report(null, items.length);

    // 4. Remove what is gone from GitLab
    const gone = indexed.map((d) => d.file_path).filter((p) => !seen.has(p));
    if (gone.length && !allListed) {
      o.log("warning", `${gone.length} documenten niet verwijderd: niet elke bron kon worden gelezen.`);
    } else {
      for (const path of gone) {
        await api.deleteDocument(o.indexToken, path);
        counts.deleted++;
      }
      if (gone.length) o.log("info", `${gone.length} documenten verwijderd die niet meer in GitLab staan.`);
    }
    report(null, items.length);
  } finally {
    unload(o.ollamaUrl, o.embedModel).catch(() => {});
  }
  return counts;
}
