// Calls to the shelly-chat server on the NAS. Always the relative /api path:
// nginx proxies it locally, Traefik routes it in production.
import type {
  ChatMessage,
  Conversation,
  ConversationSummary,
  ExpansionSource,
  IndexStatus,
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

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),
  config: () => request<ServerConfig>("/api/config"),
  indexStatus: () => request<IndexStatus>("/api/index"),

  expand: (query: string, signal?: AbortSignal) =>
    request<{ query: string; expansions: ExpansionSource[] }>("/api/expand", {
      method: "POST",
      body: JSON.stringify({ query }),
      signal,
    }),

  retrieve: (embedding: number[], embedModel: string, signal?: AbortSignal) =>
    request<{ contexts: SourceContext[] }>("/api/retrieve", {
      method: "POST",
      body: JSON.stringify({ embedding, embed_model: embedModel }),
      signal,
    }),

  conversations: () =>
    request<{ conversations: ConversationSummary[] }>("/api/conversations").then(
      (r) => r.conversations,
    ),
  conversation: (id: string) => request<Conversation>(`/api/conversations/${id}`),
  createConversation: (messages: Omit<ChatMessage, "id">[]) =>
    request<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ messages }),
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
};
