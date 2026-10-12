// Building blocks shared by the index and settings screens.
import { Box, Card, CardContent, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState, type ReactNode } from "react";

import { useAppState } from "../../appState";
import { api } from "../../lib/api";
import { hasModel } from "../../lib/ollama";
import type { IndexSettings } from "../../lib/types";

export const DEFAULT_EMBED_MODEL = "qwen3-embedding:latest";

export function Section(props: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Card sx={{ flexShrink: 0 }}>
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={4}>
          <Box>
            <Typography variant="h3" component="h2">{props.title}</Typography>
            {props.subtitle && <Typography variant="body2" sx={{ mt: 2 }}>{props.subtitle}</Typography>}
          </Box>
          {props.action}
        </Stack>
        {props.children}
      </CardContent>
    </Card>
  );
}

export function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box>
      <Typography variant="overline" component="p">{label}</Typography>
      <Typography sx={{ fontSize: 20, fontWeight: 600, color: "text.primary", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
    </Box>
  );
}

/** The INDEX_TOKEN field: needed to change anything that applies to everyone. */
export function TokenField() {
  const { settings, updateSettings } = useAppState();
  const state = useTokenState(settings.indexToken);
  return (
    <TextField
      label="Index-token van de NAS"
      type="password"
      autoComplete="off"
      value={settings.indexToken}
      onChange={(e) => updateSettings({ indexToken: e.target.value.trim() })}
      error={state === "wrong"}
      helperText={
        state === "ok"
          ? "Klopt."
          : state === "wrong"
            ? "Dit token klopt niet. Het staat als INDEX_TOKEN in de GitHub-secrets."
            : state === "checking"
              ? "Controleren…"
              : "INDEX_TOKEN uit de GitHub-secrets."
      }
      sx={{ maxWidth: 420 }}
    />
  );
}

export const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("nl-NL", { dateStyle: "medium", timeStyle: "short" }) : "—";

export type TokenState = "unknown" | "checking" | "ok" | "wrong";

/** Whether the index token in this browser is the NAS's INDEX_TOKEN (checked as it is typed). */
export function useTokenState(token: string): TokenState {
  const [state, setState] = useState<TokenState>("unknown");
  useEffect(() => {
    if (!token) {
      setState("unknown");
      return;
    }
    setState("checking");
    const t = setTimeout(() => {
      api
        .checkIndexToken(token)
        .then(() => setState("ok"))
        .catch(() => setState("wrong"));
    }, 400);
    return () => clearTimeout(t);
  }, [token]);
  return state;
}

/** Global indexing settings (model, chunking, documents folder), loaded once per screen. */
export function useIndexSettings() {
  const [data, setData] = useState<IndexSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = async () => {
    try {
      setData(await api.indexSettings());
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  useEffect(() => {
    load();
  }, []);
  return { data, error, reload: load };
}

/** The embedding model indexing uses: chosen in this browser, else the store's, else the default. */
export function useEmbedModel(data: IndexSettings | null): string {
  const { settings } = useAppState();
  return settings.embedModel || data?.meta?.embed_model || DEFAULT_EMBED_MODEL;
}

/** What still stands in the way of indexing, in words. */
export function useBlockers(data: IndexSettings | null, tokenState: TokenState, embedModel: string): string[] {
  const { ollama } = useAppState();
  const blockers: string[] = [];
  if (ollama.status !== "ok") blockers.push("Ollama is niet bereikbaar vanuit deze browser.");
  else if (!hasModel(ollama.models, embedModel)) blockers.push(`${embedModel} ontbreekt in Ollama: ollama pull ${embedModel}`);
  if (tokenState !== "ok") blockers.push("Vul het index-token van de NAS in (op het overzicht Indexen).");
  if (data && !data.documents_root_exists) blockers.push("De documentenmap is niet gekoppeld aan de server (zie DOCUMENTS_DIR).");
  return blockers;
}
