// State shared by the shell and the chat: server config, index status, the
// local Ollama's reachability and models, the conversation list and settings.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "./lib/api";
import { listModels, type OllamaModel } from "./lib/ollama";
import { useSettings, type Settings } from "./lib/settings";
import type { ConversationSummary, DocIndex, IndexStatus, ServerConfig } from "./lib/types";

export type OllamaState =
  | { status: "checking" }
  | { status: "ok"; models: OllamaModel[] }
  | { status: "unreachable"; message: string };

interface AppState {
  config: ServerConfig | null;
  configError: string | null;
  index: IndexStatus | null;
  ollama: OllamaState;
  settings: Settings;
  updateSettings: (patch: Partial<Settings>) => void;
  /** The LLM to use: the user's choice, else the server default. */
  llmModel: string;
  conversations: ConversationSummary[] | null;
  conversationsError: string | null;
  /** The named indexes; null while loading. */
  indexes: DocIndex[] | null;
  refreshIndexes: () => Promise<void>;
  refreshConversations: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  checkOllama: () => Promise<void>;
}

const Ctx = createContext<AppState | null>(null);

export function useAppState(): AppState {
  const state = useContext(Ctx);
  if (!state) throw new Error("useAppState outside AppStateProvider");
  return state;
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [settings, updateSettings] = useSettings();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [index, setIndex] = useState<IndexStatus | null>(null);
  const [ollama, setOllama] = useState<OllamaState>({ status: "checking" });
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [conversationsError, setConversationsError] = useState<string | null>(null);
  const [indexes, setIndexes] = useState<DocIndex[] | null>(null);

  const refreshIndexes = useCallback(async () => {
    try {
      setIndexes(await api.indexes());
    } catch {
      setIndexes((prev) => prev ?? []);
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const [c, i] = await Promise.all([api.config(), api.indexStatus()]);
      setConfig(c);
      setIndex(i);
      setConfigError(null);
    } catch (err) {
      setConfigError((err as Error).message);
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.conversations());
      setConversationsError(null);
    } catch (err) {
      setConversationsError((err as Error).message);
    }
  }, []);

  const checkOllama = useCallback(async () => {
    setOllama({ status: "checking" });
    try {
      setOllama({ status: "ok", models: await listModels(settings.ollamaUrl) });
    } catch (err) {
      setOllama({ status: "unreachable", message: (err as Error).message });
    }
  }, [settings.ollamaUrl]);

  useEffect(() => {
    refreshStatus();
    refreshConversations();
    refreshIndexes();
  }, [refreshStatus, refreshConversations, refreshIndexes]);

  useEffect(() => {
    checkOllama();
  }, [checkOllama]);

  const llmModel = settings.llmModel || config?.llm_model || "";

  return (
    <Ctx.Provider
      value={{
        config,
        configError,
        index,
        ollama,
        settings,
        updateSettings,
        llmModel,
        conversations,
        conversationsError,
        refreshConversations,
        indexes,
        refreshIndexes,
        refreshStatus,
        checkOllama,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
