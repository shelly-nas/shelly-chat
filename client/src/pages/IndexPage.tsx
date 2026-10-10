// Index: which GitLab sources the chat searches, and indexing them from this
// browser. The work happens here because this machine has Ollama (and the VPN
// to GitLab); the NAS only splits and stores.
import AddIcon from "@mui/icons-material/Add";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormHelperText,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Skeleton,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { useAppState } from "../appState";
import { ApiError, api } from "../lib/api";
import { resetReason, runIndex, type LogLevel, type RunCounts, type RunProgress } from "../lib/indexer";
import { hasModel } from "../lib/ollama";
import type { IndexSettings } from "../lib/types";

const DEFAULT_EMBED_MODEL = "qwen3-embedding:latest";

function Section(props: { title: string; subtitle: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Card sx={{ flexShrink: 0 }}>
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={4}>
          <Box>
            <Typography variant="h3" component="h2">{props.title}</Typography>
            <Typography variant="body2" sx={{ mt: 2 }}>{props.subtitle}</Typography>
          </Box>
          {props.action}
        </Stack>
        {props.children}
      </CardContent>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box>
      <Typography variant="overline" component="p">{label}</Typography>
      <Typography sx={{ fontSize: 20, fontWeight: 600, color: "text.primary", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
    </Box>
  );
}

const LOG_ICON: Record<LogLevel, ReactNode> = {
  info: <InfoOutlinedIcon fontSize="small" color="action" aria-hidden />,
  success: <CheckCircleOutlineIcon fontSize="small" color="success" aria-hidden />,
  warning: <WarningAmberIcon fontSize="small" color="warning" aria-hidden />,
  error: <ErrorOutlineIcon fontSize="small" color="error" aria-hidden />,
};

type TokenState = "unknown" | "checking" | "ok" | "wrong";

export default function IndexPage() {
  const { settings, updateSettings, ollama, refreshStatus, index } = useAppState();
  const [data, setData] = useState<IndexSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tokenState, setTokenState] = useState<TokenState>("unknown");
  const [newSource, setNewSource] = useState("");
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [log, setLog] = useState<{ level: LogLevel; message: string; at: Date }[]>([]);
  const [result, setResult] = useState<{ counts?: RunCounts; error?: string; stopped?: boolean } | null>(null);
  const [confirmFull, setConfirmFull] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [accessFirst] = useState(() => !settings.indexToken || !settings.gitlabToken);

  const load = useCallback(async () => {
    try {
      setData(await api.indexSettings());
      setLoadError(null);
    } catch (err) {
      setLoadError((err as Error).message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  // Check the index token whenever it changes (debounced).
  useEffect(() => {
    if (!settings.indexToken) {
      setTokenState("unknown");
      return;
    }
    setTokenState("checking");
    const t = setTimeout(() => {
      api
        .checkIndexToken(settings.indexToken)
        .then(() => setTokenState("ok"))
        .catch(() => setTokenState("wrong"));
    }, 400);
    return () => clearTimeout(t);
  }, [settings.indexToken]);

  // Leaving the page mid-run would stop it: ask first.
  useEffect(() => {
    if (!running) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [running]);

  const models = ollama.status === "ok" ? ollama.models : [];
  const embedModel = settings.embedModel || data?.meta?.embed_model || DEFAULT_EMBED_MODEL;
  const reason = data ? resetReason(data.meta, data.chunk_config, embedModel) : null;
  const embedInstalled = ollama.status === "ok" && hasModel(models, embedModel);

  const blockers: string[] = [];
  if (ollama.status !== "ok") blockers.push("Ollama is niet bereikbaar vanuit deze browser.");
  else if (!embedInstalled) blockers.push(`${embedModel} ontbreekt in Ollama: ollama pull ${embedModel}`);
  if (tokenState !== "ok") blockers.push("Vul het index-token van de NAS in.");
  if (!settings.gitlabToken) blockers.push("Vul je GitLab-token in.");
  if (data && data.sources.length === 0) blockers.push("Voeg minstens één bron toe.");

  const addSource = async () => {
    setAdding(true);
    setSourceError(null);
    try {
      await api.addSource(settings.indexToken, newSource.trim());
      setNewSource("");
      await load();
    } catch (err) {
      setSourceError(
        err instanceof ApiError && err.status === 422
          ? "Vul een volledige GitLab-URL in, zoals https://gitlab.example.com/groep/project/-/wikis."
          : (err as Error).message,
      );
    } finally {
      setAdding(false);
    }
  };

  const removeSource = async (id: number) => {
    try {
      await api.deleteSource(settings.indexToken, id);
      await load();
      setToast("Bron verwijderd. De documenten verdwijnen bij de volgende indexering.");
    } catch (err) {
      setToast(`Verwijderen mislukt: ${(err as Error).message}`);
    }
  };

  const start = async (full: boolean) => {
    setConfirmFull(false);
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setResult(null);
    setLog([]);
    setProgress(null);
    try {
      const counts = await runIndex({
        ollamaUrl: settings.ollamaUrl,
        embedModel,
        indexToken: settings.indexToken,
        gitlabToken: settings.gitlabToken,
        full,
        signal: controller.signal,
        log: (level, message) => setLog((prev) => [...prev.slice(-299), { level, message, at: new Date() }]),
        progress: setProgress,
      });
      setResult({ counts });
      setToast("Indexering voltooid");
    } catch (err) {
      setResult(controller.signal.aborted ? { stopped: true } : { error: (err as Error).message });
    } finally {
      setRunning(false);
      abortRef.current = null;
      load();
      refreshStatus();
    }
  };

  const rebuildAbbreviations = async () => {
    try {
      const r = await api.rebuildAbbreviations(settings.indexToken);
      setToast(`${r.abbreviations} afkortingen uit ${r.documents} documenten`);
      refreshStatus();
    } catch (err) {
      setToast(`Mislukt: ${(err as Error).message}`);
    }
  };

  const accessCard = (
        <Section
          title="Toegang"
          subtitle="Beide tokens worden alleen in deze browser bewaard, nooit op de NAS."
        >
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 6 }}>
            <TextField
              label="Index-token van de NAS"
              type="password"
              autoComplete="off"
              value={settings.indexToken}
              onChange={(e) => updateSettings({ indexToken: e.target.value.trim() })}
              error={tokenState === "wrong"}
              helperText={
                tokenState === "ok"
                  ? "Klopt."
                  : tokenState === "wrong"
                    ? "Dit token klopt niet. Het staat als INDEX_TOKEN in de GitHub-secrets."
                    : tokenState === "checking"
                      ? "Controleren…"
                      : "INDEX_TOKEN uit de GitHub-secrets. Nodig om de index en de bronnen te wijzigen."
              }
              fullWidth
            />
            <TextField
              label="GitLab-token"
              type="password"
              autoComplete="off"
              value={settings.gitlabToken}
              onChange={(e) => updateSettings({ gitlabToken: e.target.value.trim() })}
              helperText="Personal Access Token met read_api. Je browser haalt hiermee de documenten op."
              fullWidth
            />
          </Box>
        </Section>
  );

  const percent = progress && progress.total ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
      <Stack spacing={6} sx={{ maxWidth: 960, mx: "auto", px: { xs: 6, md: 8 }, py: { xs: 6, md: 8 } }}>
        <Box>
          <Typography variant="h2" component="h1">Index</Typography>
          <Typography variant="body2" sx={{ mt: 2 }}>
            De documenten uit GitLab die de chat doorzoekt. Indexeren gebeurt in deze browser met je eigen
            Ollama; de NAS knipt en bewaart.
          </Typography>
        </Box>

        {loadError && (
          <Alert severity="error" action={<Button size="small" onClick={load}>Opnieuw proberen</Button>}>
            Index-instellingen laden mislukt. {loadError}
          </Alert>
        )}

        {/* Status */}
        <Card>
          <CardContent>
            {index === null ? (
              <Skeleton variant="rounded" height={56} />
            ) : (
              <Stack direction="row" flexWrap="wrap" useFlexGap spacing={8}>
                <Fact label="Documenten" value={index.documents.toLocaleString("nl-NL")} />
                <Fact label="Chunks" value={index.chunks.toLocaleString("nl-NL")} />
                <Fact label="Afkortingen" value={index.abbreviations.toLocaleString("nl-NL")} />
                <Fact label="Embeddingmodel" value={index.meta?.embed_model ?? "—"} />
                <Fact
                  label="Laatst geïndexeerd"
                  value={index.last_indexed_at ? new Date(index.last_indexed_at).toLocaleString("nl-NL", { dateStyle: "medium", timeStyle: "short" }) : "—"}
                />
              </Stack>
            )}
          </CardContent>
        </Card>

        {/* Tokens first while they are missing. Decided when the page opens, so
            the card does not jump away while someone is typing in it. */}
        {accessFirst && accessCard}

        {/* Indexing */}
        <Section
          title="Indexeren"
          subtitle="Haalt nieuwe en gewijzigde documenten op en embedt ze. Ongewijzigde documenten worden overgeslagen."
        >
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 6 }}>
            <FormControl fullWidth disabled={running}>
              <InputLabel id="embed-model">Embeddingmodel</InputLabel>
              <Select
                labelId="embed-model"
                value={embedModel}
                sx={{ height: 40, "& .MuiSelect-select": { display: "flex", alignItems: "center", height: "100%", py: 0 } }}
                onChange={(e) => updateSettings({ embedModel: e.target.value })}
              >
                {[...new Set([embedModel, ...models.map((m) => m.name)])].map((name) => (
                  <MenuItem key={name} value={name}>{name}</MenuItem>
                ))}
              </Select>
              <FormHelperText>
                {reason
                  ? `Let op: ${reason}. De hele index wordt opnieuw opgebouwd.`
                  : "Vragen in de chat gebruiken automatisch hetzelfde model."}
              </FormHelperText>
            </FormControl>
            <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, pt: { md: "26px" }, flexWrap: "wrap" }}>
              {running ? (
                <Button variant="outlined" onClick={() => abortRef.current?.abort()}>Stoppen</Button>
              ) : (
                <>
                  <Button variant="contained" disabled={blockers.length > 0} onClick={() => start(false)}>
                    Indexeren
                  </Button>
                  <Button variant="outlined" disabled={blockers.length > 0} onClick={() => setConfirmFull(true)}>
                    Volledig opnieuw…
                  </Button>
                </>
              )}
            </Box>
          </Box>

          {!running && blockers.length > 0 && (
            <Alert severity="info">
              <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>Nog nodig om te indexeren</Typography>
              <Box component="ul" sx={{ m: 0, mt: 1, pl: 5 }}>
                {blockers.map((b) => <li key={b}><Typography variant="body2">{b}</Typography></li>)}
              </Box>
            </Alert>
          )}

          {(running || progress) && (
            <Box>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: "text.primary" }} noWrap>
                  {running ? (progress?.current ? `Bezig met ${progress.current}…` : "Bronnen ophalen uit GitLab…") : "Klaar"}
                </Typography>
                <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", flexShrink: 0, ml: 4 }}>
                  {progress ? `${progress.done} / ${progress.total}` : ""}
                </Typography>
              </Stack>
              <LinearProgress
                variant={progress && progress.total ? "determinate" : "indeterminate"}
                value={percent}
                sx={{ height: 6, borderRadius: 3 }}
                aria-label="Voortgang van het indexeren"
              />
              {progress && (
                <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap" sx={{ mt: 3 }}>
                  <Chip size="small" label={`${progress.counts.new} nieuw`} />
                  <Chip size="small" label={`${progress.counts.changed} gewijzigd`} />
                  <Chip size="small" label={`${progress.counts.unchanged} ongewijzigd`} />
                  <Chip size="small" label={`${progress.counts.deleted} verwijderd`} />
                  {progress.counts.failed > 0 && <Chip size="small" color="error" label={`${progress.counts.failed} mislukt`} />}
                </Stack>
              )}
              {running && (
                <Typography variant="caption" component="p" sx={{ mt: 2 }}>
                  Houd dit tabblad open tot het klaar is. Stoppen is veilig: de volgende keer gaat het verder.
                </Typography>
              )}
            </Box>
          )}

          {result?.counts && (
            <Alert severity={result.counts.failed ? "warning" : "success"}>
              Indexering voltooid: {result.counts.new} nieuw, {result.counts.changed} gewijzigd,{" "}
              {result.counts.unchanged} ongewijzigd, {result.counts.deleted} verwijderd
              {result.counts.failed ? `, ${result.counts.failed} mislukt (zie het logboek)` : ""}.
            </Alert>
          )}
          {result?.error && <Alert severity="error">Indexeren mislukt. {result.error}</Alert>}
          {result?.stopped && <Alert severity="info">Gestopt. Wat al opgeslagen was, blijft staan.</Alert>}

          {log.length > 0 && (
            <Box>
              <Typography variant="overline" component="h3">Logboek</Typography>
              <Stack
                spacing={1}
                sx={{ mt: 2, maxHeight: 280, overflowY: "auto", p: 3, borderRadius: 2, border: 1, borderColor: "divider" }}
              >
                {log.map((l, i) => (
                  <Stack key={i} direction="row" spacing={2} alignItems="flex-start">
                    {LOG_ICON[l.level]}
                    <Typography variant="body2" sx={{ color: "text.primary", overflowWrap: "anywhere" }}>
                      {l.message}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Box>
          )}

          <Box>
            <Button variant="text" size="small" disabled={running || tokenState !== "ok"} onClick={rebuildAbbreviations}>
              Afkortingen opnieuw opbouwen
            </Button>
          </Box>
        </Section>

        {/* Sources */}
        <Section
          title="Bronnen"
          subtitle="GitLab-wiki's en -repositories. Gedeeld: iedereen die indexeert gebruikt deze lijst."
        >
          {data === null ? (
            <Skeleton variant="rounded" height={80} />
          ) : data.sources.length === 0 ? (
            <Typography variant="body2">
              Nog geen bronnen. Voeg een wiki (…/-/wikis) of een repository toe; een map in een repository kan ook
              (…/-/tree/main/docs).
            </Typography>
          ) : (
            <Stack spacing={2} component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
              {data.sources.map((s) => (
                <Stack key={s.id} component="li" direction="row" alignItems="center" spacing={3} sx={{ minHeight: 44 }}>
                  <Chip size="small" label={s.kind === "wiki" ? "Wiki" : "Repository"} sx={{ bgcolor: "action.hover", color: "text.secondary", flexShrink: 0 }} />
                  <Typography variant="body2" sx={{ flex: 1, color: "text.primary", overflowWrap: "anywhere" }}>{s.url}</Typography>
                  <IconButton
                    aria-label={`Bron ${s.url} verwijderen`}
                    disabled={running || tokenState !== "ok"}
                    onClick={() => removeSource(s.id)}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </Stack>
              ))}
            </Stack>
          )}
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              addSource();
            }}
            sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}
          >
            <TextField
              label="Nieuwe bron"
              placeholder="https://gitlab.example.com/groep/project/-/wikis"
              value={newSource}
              onChange={(e) => setNewSource(e.target.value)}
              error={sourceError !== null}
              helperText={sourceError ?? (tokenState === "ok" ? " " : "Bronnen wijzigen kan met een geldig index-token.")}
              disabled={tokenState !== "ok" || running}
              fullWidth
            />
            <Button
              type="submit"
              variant="outlined"
              startIcon={<AddIcon />}
              disabled={!newSource.trim() || tokenState !== "ok" || adding || running}
              sx={{ mt: "26px", flexShrink: 0 }}
            >
              {adding ? "Toevoegen…" : "Toevoegen"}
            </Button>
          </Box>
        </Section>

        {!accessFirst && accessCard}
      </Stack>

      <Dialog open={confirmFull} onClose={() => setConfirmFull(false)} maxWidth="xs" fullWidth>
        <DialogTitle variant="h3">Index volledig opnieuw opbouwen?</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            Alle {index?.documents ?? ""} documenten worden van de NAS verwijderd en opnieuw opgehaald en geëmbed.
            Tot dat klaar is, vindt de chat minder. Gesprekken blijven bewaard.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 6, pb: 6 }}>
          <Button variant="text" onClick={() => setConfirmFull(false)}>Annuleren</Button>
          <Button variant="outlined" color="error" onClick={() => start(true)}>Opnieuw opbouwen</Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={toast !== null}
        autoHideDuration={2400}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Box>
  );
}
