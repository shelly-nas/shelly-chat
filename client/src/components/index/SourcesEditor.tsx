// The sources of one index: folders or files in the documents folder, with a
// browser to pick them. The NAS stores them relative to the documents folder;
// when that is an absolute path on the NAS (on acc and prod it is /, the whole
// file system), they are shown and typed as absolute paths.
import AddIcon from "@mui/icons-material/Add";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import { ApiError, api } from "../../lib/api";
import type { BrowseResult, DocIndex, IndexSettings } from "../../lib/types";

const MONO = "ui-monospace, Menlo, monospace";

interface Props {
  index: DocIndex;
  settings: IndexSettings | null;
  token: string;
  canEdit: boolean;
  onChanged: () => void;
  onToast: (message: string) => void;
}

/** How a stored (relative) path is shown: "/home/jelle/docs" when DOCUMENTS_DIR is "/". */
export function displayPath(documentsDir: string | undefined, path: string): string {
  const dir = (documentsDir ?? "").replace(/\/+$/, "");
  if (!(documentsDir ?? "").startsWith("/")) return path;
  return path ? `${dir}/${path}` : dir || "/";
}

export default function SourcesEditor({ index, settings, token, canEdit, onChanged, onToast }: Props) {
  const [newSource, setNewSource] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [browsing, setBrowsing] = useState<BrowseResult | null>(null);

  const absolute = settings?.documents_dir?.startsWith("/") ?? false;
  const show = (path: string) => displayPath(settings?.documents_dir, path);
  // In the text field a folder ends in "/", so the browser opens it.
  const asInput = (path: string, folder: boolean) => {
    const shown = show(path);
    return folder && !shown.endsWith("/") ? `${shown}/` : shown;
  };

  // The folder browser shows what is in the folder typed so far.
  useEffect(() => {
    if (!canEdit) return;
    const cut = newSource.lastIndexOf("/");
    const folder = cut > 0 ? newSource.slice(0, cut) : cut === 0 ? "/" : "";
    const t = setTimeout(() => {
      api.browse(token, folder).then(setBrowsing).catch(() => {});
    }, 200);
    return () => clearTimeout(t);
  }, [newSource, token, canEdit]);

  const add = async () => {
    setAdding(true);
    setError(null);
    try {
      await api.addSource(token, index.id, newSource.trim());
      setNewSource("");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Toevoegen mislukt: ${(err as Error).message}`);
    } finally {
      setAdding(false);
    }
  };

  const remove = async (sourceId: number) => {
    try {
      await api.deleteSource(token, index.id, sourceId);
      onChanged();
      onToast("Bron verwijderd. De documenten gaan bij de volgende indexering uit deze index.");
    } catch (err) {
      onToast(`Verwijderen mislukt: ${(err as Error).message}`);
    }
  };

  const dir = settings?.documents_dir?.replace(/\/+$/, "");
  return (
    <>
      {settings && (
        <Alert severity={settings.documents_root_exists ? "info" : "error"} icon={false}>
          <Typography variant="body2" sx={{ color: "text.primary" }}>
            {absolute ? (
              <>
                Een bron is een map (met alles erin) of een bestand op de NAS, met het volledige pad
                {dir ? <> binnen <strong>{dir}</strong></> : null}, bijvoorbeeld <code>{show("home/jelle/Documenten")}</code>.
              </>
            ) : (
              <>
                Paden zijn relatief aan de documentenmap{dir ? <> <strong>{dir}</strong></> : null}. Een bron{" "}
                <code>handboek</code> is dus de map handboek daarin, met alles erin.
              </>
            )}{" "}
            Ondersteund: .md, .adoc, .txt, .pdf, .docx en .doc.
          </Typography>
          {!settings.documents_root_exists && (
            <Typography variant="body2" sx={{ mt: 2, color: "text.primary" }}>
              De server ziet deze map niet. Controleer DOCUMENTS_DIR en of de map op de NAS bestaat.
            </Typography>
          )}
        </Alert>
      )}

      {index.sources.length === 0 ? (
        <Typography variant="body2">Nog geen bronnen. Kies hieronder een map of bestand.</Typography>
      ) : (
        <Stack spacing={2} component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
          {index.sources.map((s) => (
            <Stack key={s.id} component="li" direction="row" alignItems="center" spacing={3} sx={{ minHeight: 44 }}>
              <Typography variant="body2" sx={{ flex: 1, color: "text.primary", overflowWrap: "anywhere", fontFamily: MONO }}>
                {absolute ? show(s.path) : s.path || "(hele documentenmap)"}
              </Typography>
              {s.exists ? (
                <Chip
                  size="small"
                  label={`${s.documents} ${s.documents === 1 ? "document" : "documenten"}`}
                  sx={{ bgcolor: "action.hover", color: "text.secondary" }}
                />
              ) : (
                <Chip size="small" color="error" variant="outlined" icon={<ErrorOutlineIcon />} label="Bestaat niet" />
              )}
              <IconButton
                aria-label={`Bron ${show(s.path) || "documentenmap"} verwijderen`}
                disabled={!canEdit}
                onClick={() => remove(s.id)}
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
          add();
        }}
        sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}
      >
        <TextField
          label="Nieuwe bron"
          placeholder={absolute ? show("home/jelle/Documenten") : "handboek of team/renovate.pdf (leeg = hele documentenmap)"}
          value={newSource}
          onChange={(e) => {
            setNewSource(e.target.value);
            setError(null);
          }}
          error={error !== null}
          helperText={error ?? (canEdit ? "Kies hieronder, of typ een pad." : "Bronnen wijzigen kan met een geldig index-token.")}
          disabled={!canEdit}
          fullWidth
          inputProps={{ style: { fontFamily: MONO } }}
        />
        <Button type="submit" variant="outlined" startIcon={<AddIcon />} disabled={!canEdit || adding} sx={{ mt: "26px", flexShrink: 0 }}>
          {adding ? "Toevoegen…" : "Toevoegen"}
        </Button>
      </Box>

      {browsing && canEdit && (
        <Box sx={{ border: 1, borderColor: "divider", borderRadius: 2, maxHeight: 240, overflowY: "auto" }}>
          <List dense disablePadding aria-label="Inhoud van de documentenmap">
            {browsing.path && (
              <ListItemButton
                onClick={() => {
                  const up = browsing.path.includes("/") ? browsing.path.slice(0, browsing.path.lastIndexOf("/")) : "";
                  setNewSource(asInput(up, up !== "" || absolute));
                }}
              >
                <ArrowUpwardIcon fontSize="small" aria-hidden />
                <ListItemText primary="Omhoog" primaryTypographyProps={{ fontSize: 14 }} />
              </ListItemButton>
            )}
            {browsing.folders.map((f) => (
              <ListItemButton key={f} onClick={() => setNewSource(asInput(f, true))}>
                <FolderOutlinedIcon fontSize="small" aria-hidden />
                <ListItemText primary={f.split("/").pop()} primaryTypographyProps={{ fontSize: 14 }} />
              </ListItemButton>
            ))}
            {browsing.documents.map((d) => (
              <ListItemButton key={d} onClick={() => setNewSource(asInput(d, false))}>
                <DescriptionOutlinedIcon fontSize="small" aria-hidden />
                <ListItemText primary={d.split("/").pop()} primaryTypographyProps={{ fontSize: 14 }} />
              </ListItemButton>
            ))}
            {browsing.folders.length + browsing.documents.length === 0 && (
              <Typography variant="body2" sx={{ p: 4 }}>Deze map is leeg.</Typography>
            )}
          </List>
        </Box>
      )}
    </>
  );
}
