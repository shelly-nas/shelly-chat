// One index: its name, sources and ignore patterns, and updating it.
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Skeleton,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";

import { useAppState } from "../appState";
import { Section, formatDate, useBlockers, useEmbedModel, useIndexSettings, useTokenState } from "../components/index/common";
import IgnoreEditor from "../components/index/IgnoreEditor";
import RunPanel, { useIndexRun } from "../components/index/RunPanel";
import SourcesEditor from "../components/index/SourcesEditor";
import { ApiError, api } from "../lib/api";
import { resetReason } from "../lib/indexer";
import type { DocIndex } from "../lib/types";

export default function IndexDetailPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const { settings, refreshIndexes, conversations } = useAppState();
  const { data } = useIndexSettings();
  const tokenState = useTokenState(settings.indexToken);
  const embedModel = useEmbedModel(data);
  const blockers = useBlockers(data, tokenState, embedModel);

  const [index, setIndex] = useState<DocIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setIndex(await api.index(id));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? "Deze index bestaat niet (meer)." : (err as Error).message);
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  const run = useIndexRun(load);
  const canEdit = tokenState === "ok" && !run.running;
  const reason = data ? resetReason(data.meta, data.chunk_config, embedModel) : null;
  const changed = () => {
    load();
    refreshIndexes();
  };

  const rename = async () => {
    setNameError(null);
    try {
      setIndex(await api.updateIndex(settings.indexToken, id, { name: name.trim() }));
      setRenaming(false);
      refreshIndexes();
    } catch (err) {
      setNameError((err as Error).message);
    }
  };

  const remove = async () => {
    try {
      await api.deleteIndex(settings.indexToken, id);
      await refreshIndexes();
      navigate("/index");
    } catch (err) {
      setToast(`Verwijderen mislukt: ${(err as Error).message}`);
      setConfirmDelete(false);
    }
  };

  const chatCount = (conversations ?? []).filter((c) => c.index_id === id).length;

  return (
    <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
      <Stack spacing={6} sx={{ maxWidth: 960, mx: "auto", px: { xs: 6, md: 8 }, py: { xs: 6, md: 8 } }}>
        <Box>
          <Button component={RouterLink} to="/index" variant="text" size="small" startIcon={<ArrowBackIcon />} sx={{ ml: -3 }}>
            Alle indexen
          </Button>
        </Box>

        {error && <Alert severity="error">{error}</Alert>}

        {!index && !error && <Skeleton variant="rounded" height={120} />}

        {index && (
          <>
            <Stack direction="row" justifyContent="space-between" alignItems="flex-end" flexWrap="wrap" useFlexGap spacing={4}>
              <Box sx={{ minWidth: 0 }}>
                {renaming ? (
                  <Box component="form" onSubmit={(e) => { e.preventDefault(); rename(); }} sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
                    <TextField
                      autoFocus
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      error={nameError !== null}
                      helperText={nameError ?? " "}
                      inputProps={{ "aria-label": "Naam van de index" }}
                    />
                    <Button type="submit" variant="contained" disabled={!name.trim()}>Opslaan</Button>
                    <Button variant="text" onClick={() => setRenaming(false)}>Annuleren</Button>
                  </Box>
                ) : (
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Typography variant="h2" component="h1" noWrap>{index.name}</Typography>
                    <IconButton
                      aria-label="Naam wijzigen"
                      disabled={!canEdit}
                      onClick={() => {
                        setName(index.name);
                        setRenaming(true);
                      }}
                    >
                      <EditOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                )}
                <Typography variant="body2" sx={{ mt: 2 }}>
                  {index.documents} {index.documents === 1 ? "document" : "documenten"} geïndexeerd · bijgewerkt{" "}
                  {formatDate(index.last_indexed_at)} · {chatCount} {chatCount === 1 ? "gesprek" : "gesprekken"}
                </Typography>
              </Box>
              {run.running ? (
                <Button variant="outlined" onClick={run.stop}>Stoppen</Button>
              ) : (
                <Button
                  variant="contained"
                  disabled={blockers.length > 0 || index.sources.length === 0}
                  onClick={() => run.start([{ id: index.id, name: index.name }], { embedModel, full: false })}
                >
                  Index bijwerken
                </Button>
              )}
            </Stack>

            {!run.running && (blockers.length > 0 || index.sources.length === 0) && (
              <Alert severity="info">
                <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>Nog nodig om te indexeren</Typography>
                <Box component="ul" sx={{ m: 0, mt: 1, pl: 5 }}>
                  {[...blockers, ...(index.sources.length === 0 ? ["Voeg minstens één bron toe."] : [])].map((b) => (
                    <li key={b}><Typography variant="body2">{b}</Typography></li>
                  ))}
                </Box>
              </Alert>
            )}
            {reason && !run.running && (
              <Alert severity="warning">
                Het embeddingmodel of de chunkgrootte is gewijzigd ({reason}). Bijwerken leegt álle indexen; werk ze daarna
                bij via "Alle indexen bijwerken".
              </Alert>
            )}
            <RunPanel run={run} />

            <Section title="Bronnen" subtitle="Mappen (met alles erin) of losse bestanden uit de documentenmap op de NAS.">
              <SourcesEditor index={index} settings={data} token={settings.indexToken} canEdit={canEdit} onChanged={changed} onToast={setToast} />
            </Section>

            <Section
              title="Negeren"
              subtitle="Wat in de bronnen staat maar niet in deze index hoort. Wordt alleen hier bewaard; er komt geen bestand in de documentenmap."
            >
              <IgnoreEditor
                index={index}
                token={settings.indexToken}
                canEdit={canEdit}
                onSaved={(saved) => {
                  setIndex(saved);
                  refreshIndexes();
                }}
                onToast={setToast}
              />
            </Section>

            <Section title="Index verwijderen" subtitle="De gesprekken blijven leesbaar, maar je kunt er geen vragen meer in stellen. De documenten zelf op de NAS blijven staan.">
              <Box>
                <Button variant="outlined" color="error" disabled={!canEdit} onClick={() => setConfirmDelete(true)}>
                  Index verwijderen…
                </Button>
              </Box>
            </Section>
          </>
        )}
      </Stack>

      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)} maxWidth="xs" fullWidth>
        <DialogTitle variant="h3">“{index?.name}” verwijderen?</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            De index, de bronnen en de ignore-patronen verdwijnen. {chatCount > 0 && `${chatCount} gesprekken blijven leesbaar, zonder index. `}
            De bestanden in de documentenmap blijven staan.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 6, pb: 6 }}>
          <Button variant="text" onClick={() => setConfirmDelete(false)}>Annuleren</Button>
          <Button variant="outlined" color="error" onClick={remove}>Verwijderen</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={toast !== null} autoHideDuration={2400} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: "bottom", horizontal: "center" }} />
    </Box>
  );
}
