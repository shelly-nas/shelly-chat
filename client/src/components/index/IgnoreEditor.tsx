// An index's ignore patterns: gitignore syntax, stored on the NAS (no file).
import { Box, Button, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";

import { api } from "../../lib/api";
import type { DocIndex } from "../../lib/types";

interface Props {
  index: DocIndex;
  token: string;
  canEdit: boolean;
  onSaved: (index: DocIndex) => void;
  onToast: (message: string) => void;
}

export default function IgnoreEditor({ index, token, canEdit, onSaved, onToast }: Props) {
  const [value, setValue] = useState(index.ignore_patterns);
  const [saving, setSaving] = useState(false);
  useEffect(() => setValue(index.ignore_patterns), [index.id, index.ignore_patterns]);
  const dirty = value !== index.ignore_patterns;

  const save = async () => {
    setSaving(true);
    try {
      const saved = await api.updateIndex(token, index.id, { ignore_patterns: value });
      onSaved(saved);
      const total = saved.sources.reduce((n, s) => n + s.documents, 0);
      onToast(`Patronen opgeslagen: ${total} documenten in de bronnen`);
    } catch (err) {
      onToast(`Opslaan mislukt: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <TextField
        label="Ignore-patronen"
        multiline
        minRows={4}
        maxRows={16}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={!canEdit || saving}
        placeholder={"archief/\n*.tmp\nconcept*\n!concept-definitief.md"}
        inputProps={{ style: { fontFamily: "ui-monospace, Menlo, monospace", fontSize: 14 } }}
        helperText="Eén patroon per regel, zoals in .gitignore. Paden tellen vanaf de documentenmap; # is commentaar, ! haalt iets terug."
        fullWidth
      />
      <Box>
        <Typography variant="overline" component="p">Voorbeelden</Typography>
        <Stack component="ul" spacing={1} sx={{ m: 0, mt: 1, pl: 5 }}>
          {[
            ["archief/", "elke map archief, waar ook"],
            ["/bv/oud/", "alleen bv/oud in de documentenmap"],
            ["*.pdf", "alle PDF's"],
            ["!belangrijk.pdf", "maar deze toch wel"],
          ].map(([pattern, meaning]) => (
            <Typography key={pattern} component="li" variant="body2">
              <code>{pattern}</code> — {meaning}
            </Typography>
          ))}
        </Stack>
      </Box>
      {dirty && (
        <Stack direction="row" spacing={2} alignItems="center" justifyContent="flex-end">
          <Typography variant="body2" sx={{ mr: "auto" }}>Niet opgeslagen. Wordt toegepast bij de volgende indexering.</Typography>
          <Button variant="text" onClick={() => setValue(index.ignore_patterns)} disabled={saving}>Herstellen</Button>
          <Button variant="contained" onClick={save} disabled={!canEdit || saving}>
            {saving ? "Opslaan…" : "Patronen opslaan"}
          </Button>
        </Stack>
      )}
    </>
  );
}
