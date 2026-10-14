// Per-browser settings. They belong to the machine the browser runs on (its
// Ollama, its models), so they live in localStorage, not on the NAS.
import { useCallback, useState } from "react";

export interface Settings {
  ollamaUrl: string;
  /** Empty: the server's LLM_MODEL_NAME. */
  llmModel: string;
  /** Unload each model right after use, so embedder and LLM never compete for memory. */
  unloadModels: boolean;
  expandQuery: boolean;
  /** Ask the model not to think first (Ollama's think: false), like /no_think did. */
  disableThinking: boolean;
  /** INDEX_TOKEN of the NAS, needed to change the index. */
  indexToken: string;
  /** Index a new conversation starts with: the one chosen last time. */
  lastIndexId: number | "none" | null;
}

export const DEFAULT_SETTINGS: Settings = {
  ollamaUrl: "http://localhost:11434",
  llmModel: "",
  unloadModels: true,
  expandQuery: true,
  disableThinking: true,
  indexToken: "",
  lastIndexId: null,
};

const KEY = "shelly-chat.settings";

export function loadSettings(): Settings {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return { ...DEFAULT_SETTINGS, ...stored };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function useSettings(): [Settings, (patch: Partial<Settings>) => void] {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // private mode: keep it for this session only
      }
      return next;
    });
  }, []);
  return [settings, update];
}
