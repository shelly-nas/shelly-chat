// The system prompt every conversation uses. Shared and kept on the NAS; only
// the current text is stored, so a change applies to existing chats too.
import { Alert, Box, Button, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";

import { useAppState } from "../appState";
import { api } from "../lib/api";
import type { SharedSettings } from "../lib/types";

export default function SystemPromptEditor({ open }: { open: boolean }) {
  const { refreshStatus } = useAppState();
  const [saved, setSaved] = useState<SharedSettings | null>(null);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    setMessage(null);
    api
      .settings()
      .then((s) => {
        setSaved(s);
        setValue(s.system_prompt);
      })
      .catch((err) => setMessage({ ok: false, text: `Laden mislukt: ${(err as Error).message}` }));
  }, [open]);

  const save = async (prompt: string | null) => {
    setSaving(true);
    try {
      const s = await api.putSettings({ system_prompt: prompt });
      setSaved(s);
      setValue(s.system_prompt);
      setMessage({ ok: true, text: prompt === null ? "Standaardprompt hersteld." : "Opgeslagen. Geldt vanaf de volgende vraag, in elk gesprek." });
      refreshStatus();
    } catch (err) {
      setMessage({ ok: false, text: `Opslaan mislukt: ${(err as Error).message}` });
    } finally {
      setSaving(false);
    }
  };

  const dirty = saved !== null && value !== saved.system_prompt;
  return (
    <>
      <TextField
        label="Systeemprompt"
        multiline
        minRows={4}
        maxRows={14}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setMessage(null);
        }}
        disabled={saved === null || saving}
        helperText="Geldt voor iedereen en voor alle gesprekken, ook bestaande. {today} wordt de datum van vandaag."
        fullWidth
      />
      {message && <Alert severity={message.ok ? "success" : "error"}>{message.text}</Alert>}
      <Stack direction="row" spacing={2} alignItems="center">
        <Typography variant="body2" sx={{ mr: "auto" }}>
          {saved?.system_prompt_is_default ? "Dit is de standaardprompt (LLM_SYSTEM_PROMPT)." : saved ? "Aangepast." : ""}
        </Typography>
        {saved && !saved.system_prompt_is_default && (
          <Button variant="text" disabled={saving} onClick={() => save(null)}>Standaard herstellen</Button>
        )}
        <Box>
          <Button variant="contained" disabled={!dirty || saving || !value.trim()} onClick={() => save(value)}>
            {saving ? "Opslaan…" : "Opslaan"}
          </Button>
        </Box>
      </Stack>
    </>
  );
}
