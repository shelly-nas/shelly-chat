// Settings, in three parts: this browser (its Ollama, kept in localStorage),
// how answers are made, and how documents are indexed. The last two apply to
// everyone, live on the NAS and need the index token to change.
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormHelperText,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  Skeleton,
  Snackbar,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { useAppState } from "../appState";
import { Section, TokenField, useTokenState } from "../components/index/common";
import OllamaHelp from "../components/OllamaHelp";
import { StatusDot } from "../components/OllamaStatus";
import { api } from "../lib/api";
import { hasModel } from "../lib/ollama";
import { DEFAULT_SETTINGS } from "../lib/settings";
import type { SharedSettings, SharedValues } from "../lib/types";

type Key = keyof SharedValues;

interface Field {
  label: string;
  help: string;
  /** Text (multiline) or a number with these bounds; the NAS checks them again. */
  text?: boolean;
  /** On/off, shown as a switch. */
  toggle?: boolean;
  integer?: boolean;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
}

const FIELDS: Record<Key, Field> = {
  system_prompt: {
    label: "Systeemprompt",
    help: "De instructie die het taalmodel bij elke vraag meekrijgt. {today} wordt de datum van vandaag.",
    text: true,
  },
  no_answer_response: {
    label: "Antwoord zonder bronnen",
    help: "Wat de chat zegt als er niets relevants gevonden is. Alleen gebruikt als “Ook antwoorden zonder relevante bron” uit staat.",
    text: true,
  },
  llm_temperature: { label: "Temperatuur", help: "Lager is feitelijker, hoger creatiever.", min: 0, max: 2, step: 0.05 },
  llm_top_p: { label: "Top-p", help: "Kiest alleen uit de woorden die samen deze kans halen.", min: 0, max: 1, step: 0.01 },
  llm_top_k: { label: "Top-k", help: "Kiest uit hooguit zoveel waarschijnlijkste woorden.", integer: true, min: 1, max: 1000 },
  llm_num_ctx: {
    label: "Contextvenster",
    help: "Vraag, bronnen, gesprek en antwoord samen. Groter vraagt meer geheugen op je computer.",
    integer: true,
    min: 1024,
    max: 1048576,
    step: 1024,
    unit: "tokens",
  },
  llm_max_tokens: { label: "Maximale antwoordlengte", help: "Daarna stopt het antwoord.", integer: true, min: 1, max: 1048576, unit: "tokens" },
  retrieval_top_k: {
    label: "Kandidaten",
    help: "Zoveel kleine chunks worden opgehaald, voordat ze tot secties worden samengevoegd.",
    integer: true,
    min: 1,
    max: 500,
  },
  context_top_n: { label: "Bronnen per vraag", help: "Zoveel bronnen krijgt het taalmodel mee.", integer: true, min: 1, max: 100 },
  automerge_threshold: {
    label: "Merge-drempel",
    help: "Wordt dit deel van de kleine chunks van één sectie gevonden, dan krijgt het model de hele sectie.",
    min: 0,
    max: 1,
    step: 0.05,
  },
  min_similarity: {
    label: "Minimale relevantie",
    help:
      "Chunks met een lagere gelijkenis tellen niet mee; blijft er niets over, dan volgt het antwoord zonder bronnen. 0 is uit. " +
      "0,6 hoort bij \"Relevantie 60%\" bij de bronnen van een antwoord; kijk daar wat relevante stukken halen, dat verschilt per embeddingmodel.",
    min: 0,
    max: 1,
    step: 0.01,
  },
  answer_without_sources: {
    label: "Ook antwoorden zonder relevante bron",
    help:
      "Haalt geen enkele bron de minimale relevantie, dan antwoordt het taalmodel toch, gemarkeerd als buiten de bronnen. " +
      "Uit: direct het antwoord zonder bronnen, zonder het taalmodel.",
    toggle: true,
  },
  history_max_turns: {
    label: "Gespreksgeheugen",
    help: "Zoveel eerdere vragen en antwoorden gaan mee naar het taalmodel.",
    integer: true,
    min: 0,
    max: 100,
    unit: "beurten",
  },
  query_max_length: { label: "Maximale vraaglengte", help: "Langere vragen worden geweigerd.", integer: true, min: 100, max: 100000, unit: "tekens" },
  parent_chunk_size: {
    label: "Grote chunks",
    help: "Secties die het taalmodel als bron krijgt.",
    integer: true,
    min: 100,
    max: 20000,
    unit: "tokens",
  },
  child_chunk_size: {
    label: "Kleine chunks",
    help: "Hierop wordt gezocht. Meestal een kwart van de grote.",
    integer: true,
    min: 50,
    max: 20000,
    unit: "tokens",
  },
  parent_chunk_overlap: {
    label: "Overlap",
    help: "Zoveel tekst delen opeenvolgende grote chunks, zodat een zin op de grens niet wegvalt.",
    integer: true,
    min: 0,
    max: 10000,
    unit: "tokens",
  },
  max_file_mb: { label: "Maximale bestandsgrootte", help: "Grotere bestanden worden niet geïndexeerd.", integer: true, min: 1, max: 10000, unit: "MB" },
};

const CHUNK_KEYS: Key[] = ["parent_chunk_size", "child_chunk_size", "parent_chunk_overlap"];

const ANSWER_GROUPS: { title: string; keys: Key[] }[] = [
  { title: "Instructies", keys: ["system_prompt", "no_answer_response"] },
  { title: "Taalmodel", keys: ["llm_temperature", "llm_top_p", "llm_top_k", "llm_num_ctx", "llm_max_tokens"] },
  { title: "Zoeken", keys: ["retrieval_top_k", "context_top_n", "automerge_threshold", "min_similarity", "answer_without_sources"] },
  { title: "Gesprek", keys: ["history_max_turns", "query_max_length"] },
];
const INDEX_GROUPS: { title: string; keys: Key[] }[] = [
  { title: "Chunks", keys: CHUNK_KEYS },
  { title: "Bestanden", keys: ["max_file_mb"] },
];

type Draft = Partial<Record<Key, string>>;

/** The value a draft field stands for, or an error for people. */
function parse(key: Key, raw: string): { value: Value } | { error: string } {
  const f = FIELDS[key];
  if (f.toggle) return { value: raw === "true" };
  if (f.text) return raw.trim() ? { value: raw.trim() } : { error: "Mag niet leeg zijn." };
  const n = Number(raw.replace(",", "."));
  if (raw.trim() === "" || Number.isNaN(n)) return { error: "Vul een getal in." };
  if (f.integer && !Number.isInteger(n)) return { error: "Vul een geheel getal in." };
  if ((f.min !== undefined && n < f.min) || (f.max !== undefined && n > f.max)) {
    return { error: `Tussen ${f.min!.toLocaleString("nl-NL")} en ${f.max!.toLocaleString("nl-NL")}.` };
  }
  return { value: n };
}

/** The rules between settings, as the NAS checks them (app/settings.py check). */
function crossCheck(v: SharedValues): string | null {
  if (v.child_chunk_size >= v.parent_chunk_size) return "De kleine chunks moeten kleiner zijn dan de grote.";
  if (v.parent_chunk_overlap >= v.parent_chunk_size) return "De overlap moet kleiner zijn dan de grote chunks.";
  if (v.context_top_n > v.retrieval_top_k) return "Er kunnen niet meer bronnen naar het model dan er kandidaten worden opgehaald.";
  if (v.llm_max_tokens > v.llm_num_ctx) return "Een antwoord kan niet langer zijn dan het contextvenster.";
  return null;
}

type Value = string | number | boolean;

const show = (v: Value) => (typeof v === "number" ? v.toLocaleString("nl-NL") : typeof v === "boolean" ? (v ? "aan" : "uit") : v);

function SubHeading({ children }: { children: ReactNode }) {
  return (
    <Typography variant="overline" component="h3" sx={{ mb: -2 }}>
      {children}
    </Typography>
  );
}

function SwitchRow(props: { title: string; description: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <FormControlLabel
      sx={{ m: 0, alignItems: "flex-start", justifyContent: "space-between", gap: 4, minHeight: 44 }}
      labelPlacement="start"
      control={<Switch checked={props.checked} disabled={props.disabled} onChange={(e) => props.onChange(e.target.checked)} />}
      label={
        <Box>
          <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>{props.title}</Typography>
          <Typography variant="body2">{props.description}</Typography>
        </Box>
      }
    />
  );
}

function ModelCheck({ name, installed }: { name: string; installed: boolean }) {
  return (
    <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
      {installed ? (
        <CheckCircleOutlineIcon fontSize="small" color="success" aria-hidden />
      ) : (
        <ErrorOutlineIcon fontSize="small" color="warning" aria-hidden />
      )}
      <Typography variant="body2" sx={{ color: "text.primary" }}>
        {name} {installed ? "is geïnstalleerd" : "ontbreekt"}
      </Typography>
      {!installed && (
        <Typography variant="body2" component="code" sx={{ fontFamily: "monospace" }}>
          ollama pull {name}
        </Typography>
      )}
    </Stack>
  );
}

function BrowserSection() {
  const { settings, updateSettings, ollama, checkOllama, config, llmModel } = useAppState();
  const [url, setUrl] = useState(settings.ollamaUrl);
  useEffect(() => setUrl(settings.ollamaUrl), [settings.ollamaUrl]);

  const urlValid = /^https?:\/\/[^\s/]+/.test(url);
  const applyUrl = () => {
    if (urlValid && url !== settings.ollamaUrl) updateSettings({ ollamaUrl: url.replace(/\/+$/, "") });
  };
  const models = ollama.status === "ok" ? ollama.models : [];
  const embedModel = config?.embed_model;

  return (
    <Section title="Deze browser" subtitle="Ollama op deze computer maakt de vragen en antwoorden. Dit geldt direct, en alleen hier.">
      <TextField
        label="Adres van Ollama"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onBlur={applyUrl}
        onKeyDown={(e) => e.key === "Enter" && applyUrl()}
        error={!urlValid}
        helperText={
          urlValid
            ? `Meestal ${DEFAULT_SETTINGS.ollamaUrl}. Een andere computer in je netwerk kan ook.`
            : "Vul een volledig adres in, zoals http://localhost:11434."
        }
        fullWidth
      />
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={4}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <StatusDot color={ollama.status === "ok" ? "success.main" : ollama.status === "checking" ? "text.disabled" : "error.main"} />
          <Typography variant="body2" sx={{ color: "text.primary" }}>
            {ollama.status === "ok" ? `Verbonden, ${models.length} modellen` : ollama.status === "checking" ? "Controleren…" : "Niet bereikbaar"}
          </Typography>
        </Stack>
        <Button variant="text" size="small" onClick={checkOllama} disabled={ollama.status === "checking"}>
          Opnieuw controleren
        </Button>
      </Stack>
      {ollama.status === "unreachable" && (
        <Alert severity="error" icon={false}>
          <OllamaHelp ollamaUrl={settings.ollamaUrl} />
        </Alert>
      )}

      <FormControl fullWidth>
        <InputLabel id="llm-model">Taalmodel</InputLabel>
        <Select
          labelId="llm-model"
          value={settings.llmModel}
          displayEmpty
          sx={{ height: 40, "& .MuiSelect-select": { display: "flex", alignItems: "center", height: "100%", py: 0 } }}
          onChange={(e) => updateSettings({ llmModel: e.target.value })}
        >
          <MenuItem value="">Standaard van de server ({config?.llm_model ?? "…"})</MenuItem>
          {models.map((m) => (
            <MenuItem key={m.name} value={m.name}>{m.name}</MenuItem>
          ))}
          {settings.llmModel && !models.some((m) => m.name === settings.llmModel) && (
            <MenuItem value={settings.llmModel}>{settings.llmModel}</MenuItem>
          )}
        </Select>
        <FormHelperText>Schrijft de antwoorden. Elk chatmodel uit Ollama kan.</FormHelperText>
      </FormControl>
      {ollama.status === "ok" && (
        <Stack spacing={2}>
          {llmModel && <ModelCheck name={llmModel} installed={hasModel(models, llmModel)} />}
          {embedModel && <ModelCheck name={embedModel} installed={hasModel(models, embedModel)} />}
        </Stack>
      )}

      <SwitchRow
        title="Denken uitzetten"
        description="Modellen die eerst nadenken (Qwen3, gpt-oss, Gemma) antwoorden dan direct. Dat is sneller. Zet dit uit als het model bij lastige vragen eerst mag nadenken."
        checked={settings.disableThinking}
        onChange={(v) => updateSettings({ disableThinking: v })}
      />
      <SwitchRow
        title="Modellen direct ontladen"
        description="Geeft het geheugen na elke stap vrij, zodat embeddingmodel en taalmodel niet tegelijk geladen zijn. Uitzetten maakt vervolgvragen sneller als je genoeg (V)RAM hebt."
        checked={settings.unloadModels}
        onChange={(v) => updateSettings({ unloadModels: v })}
      />
      <SwitchRow
        title="Afkortingen uitschrijven"
        description="Vult bekende afkortingen in je vraag aan met hun betekenis uit de documenten, voordat er gezocht wordt."
        checked={settings.expandQuery}
        onChange={(v) => updateSettings({ expandQuery: v })}
      />

      <Box>
        <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary", mb: 1 }}>Index-token</Typography>
        <Typography variant="body2" sx={{ mb: 4 }}>
          Nodig om indexen en de instellingen hieronder te wijzigen. Het token blijft in deze browser.
        </Typography>
        <TokenField />
      </Box>
    </Section>
  );
}

function SharedSection(props: {
  title: string;
  subtitle: string;
  groups: { title: string; keys: Key[] }[];
  data: SharedSettings;
  canEdit: boolean;
  onSave: (changes: Partial<Record<Key, Value>>) => Promise<void>;
  /** Asked before saving these changes; return false to save straight away. */
  confirm?: (keys: Key[]) => boolean;
  warning?: ReactNode;
}) {
  const { data, groups } = props;
  const keys = useMemo(() => groups.flatMap((g) => g.keys), [groups]);
  const fromValues = () => Object.fromEntries(keys.map((k) => [k, String(data.values[k])])) as Draft;
  const [draft, setDraft] = useState<Draft>(fromValues);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  // A save elsewhere (or the first load) replaces what is shown.
  useEffect(() => setDraft(fromValues()), [data]);

  const parsed = Object.fromEntries(keys.map((k) => [k, parse(k, draft[k] ?? "")])) as Record<Key, ReturnType<typeof parse>>;
  const changes = Object.fromEntries(
    keys.flatMap((k) => {
      const p = parsed[k];
      return "value" in p && p.value !== data.values[k] ? [[k, p.value]] : [];
    }),
  ) as Partial<Record<Key, Value>>;
  const changedKeys = Object.keys(changes) as Key[];
  const fieldsValid = keys.every((k) => "value" in parsed[k]);
  const rule = fieldsValid ? crossCheck({ ...data.values, ...changes } as SharedValues) : null;
  const valid = fieldsValid && rule === null;
  const dirty = keys.some((k) => draft[k] !== String(data.values[k]));

  const save = async () => {
    setConfirming(false);
    setSaving(true);
    try {
      await props.onSave(changes);
    } finally {
      setSaving(false);
    }
  };

  const field = (k: Key) => {
    const f = FIELDS[k];
    const p = parsed[k];
    const atDefault = "value" in p && p.value === data.defaults[k];
    const reset = !atDefault && props.canEdit && (
      <Tooltip title="Standaardwaarde terugzetten">
        <IconButton
          aria-label={`${f.label}: standaardwaarde terugzetten`}
          size="small"
          onClick={() => setDraft((d) => ({ ...d, [k]: String(data.defaults[k]) }))}
        >
          <RestartAltIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    );
    const help = (
      <>
        {"error" in p ? p.error : f.help}
        {!f.text && <> Standaard: {show(data.defaults[k])}{f.unit ? ` ${f.unit}` : ""}.</>}
      </>
    );
    if (f.toggle) {
      return (
        <Box key={k} sx={{ gridColumn: "1 / -1" }}>
          <SwitchRow
            title={f.label}
            description={`${f.help} Standaard: ${show(data.defaults[k])}.`}
            checked={draft[k] === "true"}
            disabled={!props.canEdit || saving}
            onChange={(v) => setDraft((d) => ({ ...d, [k]: String(v) }))}
          />
        </Box>
      );
    }
    if (f.text) {
      return (
        <Box key={k} sx={{ gridColumn: "1 / -1" }}>
          <TextField
            label={f.label}
            multiline
            minRows={k === "system_prompt" ? 5 : 2}
            maxRows={16}
            value={draft[k] ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
            disabled={!props.canEdit || saving}
            error={"error" in p}
            helperText={help}
            fullWidth
          />
          {reset && (
            <Stack direction="row" justifyContent="flex-end" alignItems="center" spacing={1} sx={{ mt: 1 }}>
              <Typography variant="body2">Aangepast.</Typography>
              <Button variant="text" size="small" startIcon={<RestartAltIcon fontSize="small" />} onClick={() => setDraft((d) => ({ ...d, [k]: String(data.defaults[k]) }))}>
                Standaardtekst terugzetten
              </Button>
            </Stack>
          )}
        </Box>
      );
    }
    return (
      <TextField
        key={k}
        label={f.label}
        value={draft[k] ?? ""}
        onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
        disabled={!props.canEdit || saving}
        error={"error" in p}
        helperText={help}
        slotProps={{
          htmlInput: { inputMode: f.integer ? "numeric" : "decimal", "aria-label": f.label },
          input: {
            endAdornment: (f.unit || reset) && (
              <InputAdornment position="end" sx={{ gap: 1 }}>
                {reset}
                {f.unit && <Typography variant="body2">{f.unit}</Typography>}
              </InputAdornment>
            ),
          },
        }}
        fullWidth
      />
    );
  };

  return (
    <Section title={props.title} subtitle={props.subtitle}>
      {!props.canEdit && (
        <Alert severity="info">Vul bij "Deze browser" het index-token in om dit te wijzigen. Deze instellingen gelden voor iedereen.</Alert>
      )}
      {props.warning}
      {groups.map((g) => (
        <Stack key={g.title} spacing={4}>
          <SubHeading>{g.title}</SubHeading>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, columnGap: 6, rowGap: 4 }}>
            {g.keys.map(field)}
          </Box>
        </Stack>
      ))}
      {dirty && (
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          alignItems={{ xs: "stretch", sm: "center" }}
          sx={{ position: "sticky", bottom: 0, py: 3, bgcolor: "background.paper", borderTop: 1, borderColor: "divider", mx: -6, px: 6, mb: -6 }}
        >
          <Typography variant="body2" sx={{ mr: "auto" }}>
            {rule ??
              (valid
                ? `${changedKeys.length} ${changedKeys.length === 1 ? "wijziging" : "wijzigingen"}, nog niet opgeslagen.`
                : "Controleer de rood gemarkeerde velden.")}
          </Typography>
          <Button variant="text" disabled={saving} onClick={() => setDraft(fromValues())}>
            Ongedaan maken
          </Button>
          <Button
            variant="contained"
            disabled={!props.canEdit || saving || !valid || changedKeys.length === 0}
            onClick={() => (props.confirm?.(changedKeys) ? setConfirming(true) : save())}
          >
            {saving ? "Opslaan…" : "Opslaan"}
          </Button>
        </Stack>
      )}

      <Dialog open={confirming} onClose={() => setConfirming(false)} maxWidth="xs" fullWidth>
        <DialogTitle variant="h3">Chunkgrootte wijzigen?</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            Chunks van twee groottes gaan niet samen. Bij de volgende indexering worden daarom alle indexen leeggemaakt en
            opnieuw opgebouwd. Tot dat klaar is, vindt de chat niets meer.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 6, pb: 6 }}>
          <Button variant="text" onClick={() => setConfirming(false)}>Annuleren</Button>
          <Button variant="outlined" color="error" onClick={save}>Opslaan</Button>
        </DialogActions>
      </Dialog>
    </Section>
  );
}

export default function SettingsPage() {
  const { settings, refreshStatus, index, ollama, checkOllama } = useAppState();
  const tokenState = useTokenState(settings.indexToken);
  const [data, setData] = useState<SharedSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = () =>
    api
      .settings()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError((err as Error).message));
  useEffect(() => {
    load();
    if (ollama.status !== "ok") checkOllama();
  }, []);

  const save = async (changes: Partial<Record<Key, Value>>) => {
    try {
      setData(await api.putSettings(settings.indexToken, changes));
      const indexing = Object.keys(changes).some((k) => INDEX_GROUPS.some((g) => g.keys.includes(k as Key)));
      setToast(indexing ? "Opgeslagen. Geldt vanaf de volgende indexering." : "Opgeslagen. Geldt vanaf de volgende vraag, in elk gesprek.");
      refreshStatus();
    } catch (err) {
      setToast(`Opslaan mislukt: ${(err as Error).message}`);
    }
  };

  const canEdit = tokenState === "ok";
  const meta = index?.meta;
  const chunksDiffer =
    meta && data && CHUNK_KEYS.some((k) => meta[k as keyof typeof meta] !== data.values[k]);

  return (
    <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
      <Stack spacing={6} sx={{ maxWidth: 960, mx: "auto", px: { xs: 6, md: 8 }, py: { xs: 6, md: 8 } }}>
        <Box>
          <Typography variant="h2" component="h1">Instellingen</Typography>
          <Typography variant="body2" sx={{ mt: 2 }}>
            Wat bij deze browser hoort, staat bovenaan. De rest staat op de NAS en geldt voor iedereen; de standaardwaarden
            komen uit de omgeving van de server.
          </Typography>
        </Box>

        <BrowserSection />

        {error && (
          <Alert severity="error" action={<Button size="small" onClick={load}>Opnieuw proberen</Button>}>
            Instellingen laden mislukt. {error}
          </Alert>
        )}
        {!data && !error && <Skeleton variant="rounded" height={320} />}
        {data && (
          <>
            <SharedSection
              title="Antwoorden"
              subtitle="Hoe de chat zoekt en antwoordt. Geldt voor iedereen en voor alle gesprekken, ook bestaande."
              groups={ANSWER_GROUPS}
              data={data}
              canEdit={canEdit}
              onSave={save}
            />
            <SharedSection
              title="Indexeren"
              subtitle="Hoe documenten in stukken worden geknipt. Geldt voor alle indexen samen."
              groups={INDEX_GROUPS}
              data={data}
              canEdit={canEdit}
              onSave={save}
              confirm={(keys) => keys.some((k) => CHUNK_KEYS.includes(k)) && !!meta}
              warning={
                chunksDiffer && (
                  <Alert severity="warning">
                    De indexen zijn gebouwd met andere chunkgroottes ({meta!.parent_chunk_size} / {meta!.child_chunk_size} /{" "}
                    {meta!.parent_chunk_overlap}). Bij de volgende indexering worden ze opnieuw opgebouwd.
                  </Alert>
                )
              }
            />
          </>
        )}
      </Stack>
      <Snackbar
        open={toast !== null}
        autoHideDuration={3000}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Box>
  );
}
