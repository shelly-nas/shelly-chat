import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState, type ReactNode } from "react";

import { useAppState } from "../appState";
import { hasModel } from "../lib/ollama";
import { DEFAULT_SETTINGS } from "../lib/settings";
import OllamaHelp from "./OllamaHelp";
import { StatusDot } from "./OllamaStatus";

function Section({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <Card sx={{ flexShrink: 0 }}>
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Box>
          <Typography variant="h3" component="h2">{title}</Typography>
          <Typography variant="body2" sx={{ mt: 2 }}>{subtitle}</Typography>
        </Box>
        {children}
      </CardContent>
    </Card>
  );
}

function SwitchRow(props: { title: string; description: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <FormControlLabel
      sx={{ m: 0, alignItems: "flex-start", justifyContent: "space-between", gap: 4, minHeight: 44 }}
      labelPlacement="start"
      control={<Switch checked={props.checked} onChange={(e) => props.onChange(e.target.checked)} />}
      label={
        <Box>
          <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>{props.title}</Typography>
          <Typography variant="body2">{props.description}</Typography>
        </Box>
      }
    />
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={4}>
      <Typography variant="body2">{label}</Typography>
      <Typography variant="body2" sx={{ color: "text.primary", fontVariantNumeric: "tabular-nums", textAlign: "right" }}>
        {value}
      </Typography>
    </Stack>
  );
}

function ModelCheck({ name, installed }: { name: string; installed: boolean }) {
  return (
    <Stack direction="row" spacing={2} alignItems="center">
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

export default function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, updateSettings, ollama, checkOllama, config, index, refreshStatus, llmModel } = useAppState();
  const [url, setUrl] = useState(settings.ollamaUrl);

  useEffect(() => {
    if (open) {
      setUrl(settings.ollamaUrl);
      refreshStatus();
      checkOllama();
    }
    // Refresh on open only.
  }, [open]);

  const urlValid = /^https?:\/\/[^\s/]+/.test(url);
  const applyUrl = () => {
    if (urlValid && url !== settings.ollamaUrl) updateSettings({ ollamaUrl: url.replace(/\/+$/, "") });
  };

  const models = ollama.status === "ok" ? ollama.models : [];
  const embedModel = config?.embed_model;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth scroll="paper">
      <DialogTitle variant="h2" component="h1" sx={{ px: 6, pt: 6, pb: 2 }}>
        Instellingen
        <Typography variant="body2" sx={{ mt: 2 }}>
          Wijzigingen gelden direct en alleen in deze browser.
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ px: 6, display: "flex", flexDirection: "column", gap: 6, bgcolor: "background.default", pt: "24px !important" }}>
        <Section
          title="Ollama op deze computer"
          subtitle="De vraag en het antwoord worden hier gemaakt, niet op de NAS."
        >
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
              <StatusDot
                color={ollama.status === "ok" ? "success.main" : ollama.status === "checking" ? "text.disabled" : "error.main"}
              />
              <Typography variant="body2" sx={{ color: "text.primary" }}>
                {ollama.status === "ok"
                  ? `Verbonden, ${models.length} modellen`
                  : ollama.status === "checking"
                    ? "Controleren…"
                    : "Niet bereikbaar"}
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
                <MenuItem key={m.name} value={m.name}>
                  {m.name}
                </MenuItem>
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
        </Section>

        <Section
          title="Index op de NAS"
          subtitle="Bronnen en indexeren staan op het scherm Index in de zijbalk."
        >
          {index === null ? (
            <Typography variant="body2">Laden…</Typography>
          ) : index.meta === null ? (
            <Alert severity="info">Er is nog niets geïndexeerd.</Alert>
          ) : (
            <Stack spacing={2}>
              <Fact label="Documenten" value={index.documents.toLocaleString("nl-NL")} />
              <Fact label="Chunks" value={index.chunks.toLocaleString("nl-NL")} />
              <Fact label="Afkortingen" value={index.abbreviations.toLocaleString("nl-NL")} />
              <Fact label="Embeddingmodel" value={`${index.meta.embed_model} (${index.meta.embed_dimensions} dim.)`} />
              <Fact label="Chunkgrootte" value={`${index.meta.parent_chunk_size} / ${index.meta.child_chunk_size} tokens`} />
              <Fact
                label="Laatst geïndexeerd"
                value={index.last_indexed_at ? new Date(index.last_indexed_at).toLocaleString("nl-NL") : "—"}
              />
            </Stack>
          )}
        </Section>
      </DialogContent>
      <DialogActions sx={{ px: 6, py: 4 }}>
        <Button variant="contained" onClick={onClose}>
          Klaar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
