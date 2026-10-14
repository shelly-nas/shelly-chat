// Calls to the shelly-chat server on the NAS. Always the relative /api path:
// nginx proxies it locally, Traefik routes it in production.
import type {
  ChatMessage,
  Conversation,
  ConversationSummary,
  ExpansionSource,
  BrowseResult,
  DocIndex,
  IndexSettings,
  IndexSource,
  SharedSettings,
  SharedValues,
  IndexStatus,
  PrepareResult,
  ServerConfig,
  SourceContext,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // keep statusText
    }
    throw new ApiError(detail, res.status);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),
  config: () => request<ServerConfig>("/api/config"),
  indexStatus: () => request<IndexStatus>("/api/index"),

  expand: (query: string, indexId: number, signal?: AbortSignal) =>
    request<{ query: string; expansions: ExpansionSource[] }>("/api/expand", {
      method: "POST",
      body: JSON.stringify({ query, index_id: indexId }),
      signal,
    }),

  retrieve: (embedding: number[], embedModel: string, indexId: number, signal?: AbortSignal) =>
    request<{ contexts: SourceContext[] }>("/api/retrieve", {
      method: "POST",
      body: JSON.stringify({ embedding, embed_model: embedModel, index_id: indexId }),
      signal,
    }),

  conversations: () =>
    request<{ conversations: ConversationSummary[] }>("/api/conversations").then(
      (r) => r.conversations,
    ),
  conversation: (id: string) => request<Conversation>(`/api/conversations/${id}`),
  createConversation: (indexId: number | null, messages: Omit<ChatMessage, "id">[]) =>
    request<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ index_id: indexId, messages }),
    }),
  appendMessages: (id: string, messages: Omit<ChatMessage, "id">[]) =>
    request<{ messages: ChatMessage[] }>(`/api/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ messages }),
    }),
  renameConversation: (id: string, title: string) =>
    request<ConversationSummary>(`/api/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: string) =>
    request<void>(`/api/conversations/${id}`, { method: "DELETE" }),

  // Index. Everything that changes it needs the NAS's INDEX_TOKEN.
  indexSettings: () => request<IndexSettings>("/api/index/settings"),
  checkIndexToken: (token: string) =>
    request<{ ok: boolean }>("/api/index/auth", { headers: bearer(token) }),
  browse: (token: string, path: string) =>
    request<BrowseResult>(`/api/index/browse?path=${encodeURIComponent(path)}`, { headers: bearer(token) }),
  putIndexMeta: (token: string, meta: { embed_model: string; embed_dimensions: number; reset: boolean }) =>
    request<unknown>("/api/index/meta", { method: "PUT", headers: bearer(token), body: JSON.stringify(meta) }),
  indexedDocuments: (token: string) =>
    request<{ documents: { file_path: string; content_hash: string }[] }>("/api/index/documents", {
      headers: bearer(token),
    }).then((r) => r.documents),
  prepareDocument: (token: string, filePath: string, indexId: number, signal?: AbortSignal) =>
    request<PrepareResult>("/api/index/prepare", {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify({ file_path: filePath, index_id: indexId }),
      signal,
    }),
  putDocument: (token: string, document: object, signal?: AbortSignal) =>
    request<{ chunks: number; abbreviations: number }>("/api/index/documents", {
      method: "PUT",
      headers: bearer(token),
      body: JSON.stringify(document),
      signal,
    }),
  rebuildAbbreviations: (token: string) =>
    request<{ documents: number; abbreviations: number }>("/api/index/abbreviations", {
      method: "POST",
      headers: bearer(token),
    }),

  // Named indexes
  indexes: () => request<{ indexes: DocIndex[] }>("/api/indexes").then((r) => r.indexes),
  index: (id: number) => request<DocIndex>(`/api/indexes/${id}`),
  createIndex: (token: string, name: string) =>
    request<DocIndex>("/api/indexes", { method: "POST", headers: bearer(token), body: JSON.stringify({ name }) }),
  updateIndex: (token: string, id: number, change: { name?: string; ignore_patterns?: string }) =>
    request<DocIndex>(`/api/indexes/${id}`, { method: "PATCH", headers: bearer(token), body: JSON.stringify(change) }),
  deleteIndex: (token: string, id: number) =>
    request<void>(`/api/indexes/${id}`, { method: "DELETE", headers: bearer(token) }),
  addSource: (token: string, indexId: number, path: string) =>
    request<IndexSource>(`/api/indexes/${indexId}/sources`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify({ path }),
    }),
  deleteSource: (token: string, indexId: number, sourceId: number) =>
    request<void>(`/api/indexes/${indexId}/sources/${sourceId}`, { method: "DELETE", headers: bearer(token) }),
  indexFiles: (token: string, indexId: number) =>
    request<{ files: string[]; missing: string[] }>(`/api/indexes/${indexId}/files`, { headers: bearer(token) }),
  pruneIndex: (token: string, indexId: number, keep: string[]) =>
    request<{ removed: number; deleted_documents: number }>(`/api/indexes/${indexId}/prune`, {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify({ keep }),
    }),

  // Shared settings
  settings: () => request<SharedSettings>("/api/settings"),
  /** Only the keys to change; null goes back to the default. */
  putSettings: (token: string, changes: Partial<Record<keyof SharedValues, string | number | boolean | null>>) =>
    request<SharedSettings>("/api/settings", { method: "PUT", body: JSON.stringify(changes), headers: bearer(token) }),
};
