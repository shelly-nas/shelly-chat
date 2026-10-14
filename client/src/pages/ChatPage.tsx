import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import SourceOutlinedIcon from "@mui/icons-material/SourceOutlined";
import CloseIcon from "@mui/icons-material/Close";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  IconButton,
  Skeleton,
  Snackbar,
  Stack,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useAppState } from "../appState";
import MessageView, { type ViewMessage } from "../components/MessageView";
import Readiness from "../components/Readiness";
import SourcesPanel from "../components/SourcesPanel";
import { ApiError, api } from "../lib/api";
import { randomId } from "../lib/id";
import { OllamaError } from "../lib/ollama";
import { ask, type Stage } from "../lib/rag";

function describeError(err: unknown, ollamaUrl: string, llmModel: string): ViewMessage["error"] {
  if (err instanceof OllamaError) {
    if (err.kind === "unreachable") {
      return {
        title: "Ollama niet bereikbaar",
        detail: `De browser kan Ollama op ${ollamaUrl} niet bereiken. Draait Ollama, en staat deze pagina in OLLAMA_ORIGINS?`,
        ollama: true,
      };
    }
    if (err.kind === "model") {
      return {
        title: "Model niet gevonden",
        detail: `${err.message}. Installeer het met ollama pull, of kies een ander model in de instellingen (nu ${llmModel}).`,
        ollama: true,
      };
    }
    return { title: "Ollama gaf een fout", detail: err.message, ollama: true };
  }
  if (err instanceof ApiError) {
    return { title: "De NAS gaf een fout", detail: err.message, ollama: false };
  }
  return { title: "Er ging iets mis", detail: (err as Error).message, ollama: false };
}

export default function ChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  const wide = useMediaQuery(theme.breakpoints.up("lg"));
  const app = useAppState();
  const { config, settings, updateSettings, llmModel, refreshConversations, conversations, indexes } = app;

  const [messages, setMessages] = useState<ViewMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [stage, setStage] = useState<Stage | null>(null);
  const [busy, setBusy] = useState(false);
  const [sourcesFor, setSourcesFor] = useState<string | null>(null);
  const [sourcesDialog, setSourcesDialog] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  // An existing conversation's index, fixed since it started (null: none, or deleted).
  const [conversationIndexId, setConversationIndexId] = useState<number | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  // Set right after this page created a conversation, so navigating to its
  // URL does not reload what is already on screen.
  const createdRef = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    // The conversation this page just created: everything is on screen already.
    if (id && createdRef.current === id) return;
    createdRef.current = null;
    abortRef.current?.abort();
    setSourcesFor(null);
    setInput("");
    if (!id) {
      setMessages([]);
      setLoadError(null);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const conversation = await api.conversation(id);
      setMessages(conversation.messages);
      setConversationIndexId(conversation.index_id);
      const lastWithSources = [...conversation.messages].reverse().find((m) => m.sources?.length);
      setSourcesFor(lastWithSources?.id ?? null);
    } catch (err) {
      setMessages([]);
      setLoadError(err instanceof ApiError && err.status === 404 ? "Dit gesprek bestaat niet (meer)." : (err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const update = (msgId: string, patch: Partial<ViewMessage> | ((m: ViewMessage) => Partial<ViewMessage>)) =>
    setMessages((prev) => prev.map((m) => (m.id === msgId ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)));

  // A new conversation starts with the index chosen last time, if it still
  // exists. An index is optional: without one the model answers without sources.
  const chosenIndexId =
    settings.lastIndexId === "none"
      ? null
      : (indexes?.find((i) => i.id === settings.lastIndexId)?.id ?? indexes?.[0]?.id ?? null);
  const indexId = id ? conversationIndexId : chosenIndexId;
  const activeIndex = indexes?.find((i) => i.id === indexId) ?? null;

  const send = async (question: string, base: ViewMessage[] = messages) => {
    if (!question.trim() || busy || !config) return;
    const history = base.filter((m) => !m.error && !m.pending && !m.stopped);
    const userId = randomId();
    const answerId = randomId();
    setMessages([
      ...base.filter((m) => !m.error),
      { id: userId, role: "user", content: question },
      { id: answerId, role: "assistant", content: "", pending: true, model: llmModel },
    ]);
    setInput("");
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const result = await ask({
        question,
        indexId,
        history,
        config,
        ollamaUrl: settings.ollamaUrl,
        llmModel,
        expandQuery: settings.expandQuery,
        unloadModels: settings.unloadModels,
        think: !settings.disableThinking,
        signal: controller.signal,
        onStage: setStage,
        onExpansions: (effective_query, expansions) => update(userId, { effective_query, expansions }),
        onSources: (sources) => {
          update(answerId, { sources });
          setSourcesFor(answerId);
        },
        onToken: (token) => update(answerId, (m) => ({ content: m.content + token })),
        onNotice: (notice) => update(answerId, { notice }),
      });
      update(answerId, { pending: false, duration_ms: result.durationMs || null, timings: result.timings });

      const toSave = [
        { role: "user" as const, content: question, effective_query: result.effectiveQuery, expansions: result.expansions },
        {
          role: "assistant" as const,
          content: result.answer,
          sources: result.sources,
          model: llmModel,
          duration_ms: result.durationMs || null,
          timings: result.timings,
        },
      ];
      try {
        if (id) {
          await api.appendMessages(id, toSave);
        } else {
          const created = await api.createConversation(indexId, toSave);
          createdRef.current = created.id;
          setConversationIndexId(indexId);
          navigate(`/c/${created.id}`, { replace: true });
        }
        refreshConversations();
      } catch (err) {
        setToast(`Antwoord niet opgeslagen op de NAS: ${(err as Error).message}`);
      }
    } catch (err) {
      if (controller.signal.aborted) {
        update(answerId, (m) => (m.content ? { pending: false, stopped: true } : { pending: false, stopped: true, content: "_Gestopt._" }));
      } else {
        update(answerId, { pending: false, error: describeError(err, settings.ollamaUrl, llmModel) });
      }
    } finally {
      setBusy(false);
      setStage(null);
      abortRef.current = null;
    }
  };

  const retry = () => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    // Ask again without the failed pair; send() adds it back.
    send(lastUser.content, messages.slice(0, messages.lastIndexOf(lastUser)));
  };

  const title = useMemo(() => {
    if (!id) return "Nieuw gesprek";
    return conversations?.find((c) => c.id === id)?.title ?? (loading ? "" : "Gesprek");
  }, [id, conversations, loading]);

  const selectedSources = messages.find((m) => m.id === sourcesFor)?.sources ?? [];
  const showSources = (msgId: string) => {
    setSourcesFor(msgId);
    if (!wide) setSourcesDialog(true);
  };

  const empty = !loading && !loadError && messages.length === 0;

  return (
    <Box sx={{ flex: 1, minHeight: 0, display: "flex" }}>
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        {/* Page header */}
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="flex-end"
          flexWrap="wrap"
          useFlexGap
          spacing={4}
          sx={{ px: { xs: 6, md: 8 }, pt: { xs: 6, md: 8 }, pb: 4 }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h2" component="h1" noWrap>
              {title || <Skeleton width={240} />}
            </Typography>
            <Typography variant="body2" sx={{ mt: 2 }}>
              Antwoorden van {llmModel || "Ollama"} op je eigen computer,{" "}
              {activeIndex ? `met bronnen uit “${activeIndex.name}”.` : "zonder index: zonder bronnen uit je documenten."}
            </Typography>
          </Box>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
            {!id ? (
              <FormControl size="small" sx={{ minWidth: 220 }} disabled={busy}>
                <InputLabel id="chat-index">Doorzoek index</InputLabel>
                <Select
                  labelId="chat-index"
                  value={chosenIndexId ?? "none"}
                  sx={{ height: 40, "& .MuiSelect-select": { display: "flex", alignItems: "center", height: "100%", py: 0 } }}
                  onChange={(e) => updateSettings({ lastIndexId: e.target.value === "none" ? "none" : Number(e.target.value) })}
                >
                  <MenuItem value="none">Geen index (zonder bronnen)</MenuItem>
                  {indexes?.map((i) => (
                    <MenuItem key={i.id} value={i.id}>
                      {i.name} ({i.documents})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : (
              !loading && !loadError && (
                <Chip
                  icon={<SourceOutlinedIcon aria-hidden />}
                  label={activeIndex ? `Index: ${activeIndex.name}` : "Zonder index"}
                  variant="outlined"
                  sx={{ height: 32 }}
                  title="De index van een gesprek ligt vast zodra het begint."
                />
              )
            )}
            {!wide && selectedSources.length > 0 && (
              <Button variant="outlined" startIcon={<ArticleOutlinedIcon />} onClick={() => setSourcesDialog(true)}>
                Bronnen ({selectedSources.length})
              </Button>
            )}
          </Stack>
        </Stack>

        {/* Messages */}
        <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", px: { xs: 6, md: 8 } }}>
          <Stack spacing={8} sx={{ maxWidth: 760, mx: "auto", py: 4 }}>
            {loading && (
              <Stack spacing={4}>
                <Skeleton variant="rounded" height={48} sx={{ alignSelf: "flex-end", width: "60%" }} />
                <Skeleton variant="rounded" height={120} />
              </Stack>
            )}
            {loadError && (
              <Alert
                severity="error"
                action={
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="text" onClick={() => navigate("/")}>Nieuw gesprek</Button>
                    <Button size="small" variant="outlined" onClick={load}>Opnieuw proberen</Button>
                  </Stack>
                }
              >
                Gesprek laden mislukt. {loadError}
              </Alert>
            )}
            {empty && (
              <Stack spacing={6} sx={{ pt: { xs: 4, md: 12 } }}>
                <Box>
                  <Typography variant="h1">Waar kan ik je mee helpen?</Typography>
                  <Typography variant="body1" sx={{ mt: 3, color: "text.secondary" }}>
                    Stel een vraag. Je computer maakt het antwoord met Ollama; met een index zoekt de NAS er
                    bronnen uit je documenten bij. De NAS bewaart het gesprek.
                  </Typography>
                </Box>
                <Readiness index={activeIndex} />
              </Stack>
            )}
            {messages.map((m) => (
              <MessageView
                key={m.id}
                message={m}
                stage={stage}
                sourcesSelected={m.id === sourcesFor}
                onShowSources={() => showSources(m.id)}
                onRetry={retry}
                onHelp={() => navigate("/instellingen")}
              />
            ))}
            <div ref={endRef} />
          </Stack>
        </Box>

        {/* Composer */}
        <Box sx={{ px: { xs: 6, md: 8 }, pb: { xs: 4, md: 6 }, pt: 2 }}>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            sx={{ maxWidth: 760, mx: "auto", display: "flex", gap: 2, alignItems: "flex-end" }}
          >
            <TextField
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder={activeIndex ? "Stel een vraag over je documenten…" : "Stel een vraag…"}
              multiline
              maxRows={6}
              fullWidth
              disabled={!config}
              inputProps={{ "aria-label": "Je vraag", maxLength: config?.query_max_length }}
            />
            {busy ? (
              <Button variant="outlined" onClick={() => abortRef.current?.abort()} sx={{ flexShrink: 0 }}>
                Stoppen
              </Button>
            ) : (
              <Button type="submit" variant="contained" disabled={!input.trim() || !config} sx={{ flexShrink: 0 }}>
                Versturen
              </Button>
            )}
          </Box>
        </Box>
      </Box>

      {/* Sources: a side panel on wide screens, a dialog otherwise */}
      {wide && (messages.length > 0 || selectedSources.length > 0) && (
        <Box
          component="aside"
          aria-label="Bronnen"
          sx={{ width: 360, flexShrink: 0, borderLeft: 1, borderColor: "divider", bgcolor: "background.paper" }}
        >
          <SourcesPanel sources={selectedSources} />
        </Box>
      )}
      <Dialog open={!wide && sourcesDialog} onClose={() => setSourcesDialog(false)} fullWidth maxWidth="sm">
        <Stack direction="row" justifyContent="flex-end" sx={{ px: 2, pt: 2 }}>
          <IconButton aria-label="Bronnen sluiten" onClick={() => setSourcesDialog(false)}>
            <CloseIcon />
          </IconButton>
        </Stack>
        <Box sx={{ height: "65vh", mt: -6 }}>
          <SourcesPanel sources={selectedSources} />
        </Box>
      </Dialog>

      <Snackbar
        open={toast !== null}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Box>
  );
}
