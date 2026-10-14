// Indexes: the named indexes ("Mijn BV"), and what they share - the token,
// the embedding model and rebuilding everything. Each index has its own page
// for its sources and ignore patterns.
import AddIcon from "@mui/icons-material/Add";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Dialog,
  Link,
  DialogActions,
  DialogContent,
  DialogTitle,
  Skeleton,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";

import { useAppState } from "../appState";
import {
  Fact,
  Section,
  TokenField,
  formatDate,
  useBlockers,
  useEmbedModel,
  useIndexSettings,
  useTokenState,
} from "../components/index/common";
import RunPanel, { useIndexRun } from "../components/index/RunPanel";
import { api } from "../lib/api";
import { resetReason } from "../lib/indexer";

export default function IndexesPage() {
  const { settings, index: status, indexes, refreshIndexes, refreshStatus } = useAppState();
  const navigate = useNavigate();
  const { data, error, reload } = useIndexSettings();
  const tokenState = useTokenState(settings.indexToken);
  const embedModel = useEmbedModel(data);
  const blockers = useBlockers(data, tokenState, embedModel);
  const run = useIndexRun(reload);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [confirmFull, setConfirmFull] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  // Token first while it is missing; decided once, so the card does not jump while typing.
  const [tokenFirst] = useState(() => !settings.indexToken);

  const reason = data ? resetReason(data.meta, data.chunk_config, embedModel) : null;
  const all = (indexes ?? []).map((i) => ({ id: i.id, name: i.name }));

  const create = async () => {
    setCreateError(null);
    try {
      const created = await api.createIndex(settings.indexToken, newName.trim());
      await refreshIndexes();
      setCreating(false);
      setNewName("");
      navigate(`/index/${created.id}`);
    } catch (err) {
      setCreateError((err as Error).message);
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

  const tokenCard = (
    <Section title="Toegang" subtitle="Nodig om indexen te maken, te wijzigen en te indexeren. Het token blijft in deze browser.">
      <TokenField />
    </Section>
  );

  return (
    <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
      <Stack spacing={6} sx={{ maxWidth: 960, mx: "auto", px: { xs: 6, md: 8 }, py: { xs: 6, md: 8 } }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-end" flexWrap="wrap" useFlexGap spacing={4}>
          <Box>
            <Typography variant="h2" component="h1">Indexen</Typography>
            <Typography variant="body2" sx={{ mt: 2 }}>
              Elke index is een eigen verzameling documenten. Bij een nieuw gesprek kies je welke index het doorzoekt.
            </Typography>
          </Box>
          <Button variant="contained" startIcon={<AddIcon />} disabled={tokenState !== "ok"} onClick={() => setCreating(true)}>
            Nieuwe index
          </Button>
        </Stack>

        {error && (
          <Alert severity="error" action={<Button size="small" onClick={reload}>Opnieuw proberen</Button>}>
            Index-instellingen laden mislukt. {error}
          </Alert>
        )}

        {tokenFirst && tokenCard}

        {/* The indexes */}
        {indexes === null ? (
          <Skeleton variant="rounded" height={96} />
        ) : indexes.length === 0 ? (
          <Card>
            <CardContent>
              <Typography variant="h3" component="h2">Nog geen indexen</Typography>
              <Typography variant="body2" sx={{ mt: 2 }}>
                Maak een index, bijvoorbeeld "Mijn BV", en kies welke mappen erin horen. Daarna kun je er vragen over stellen.
              </Typography>
              <Button variant="outlined" startIcon={<AddIcon />} sx={{ mt: 4 }} disabled={tokenState !== "ok"} onClick={() => setCreating(true)}>
                Nieuwe index
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 6 }}>
            {indexes.map((i) => (
              <Card key={i.id} sx={{ "&:hover": { boxShadow: (t) => (t.palette.mode === "dark" ? "none" : "0 8px 24px rgba(18,22,28,.12)"), borderColor: "divider" } }}>
                <CardActionArea onClick={() => navigate(`/index/${i.id}`)} sx={{ height: "100%" }}>
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
                      <Typography variant="h3" component="h2" noWrap>{i.name}</Typography>
                      <ChevronRightIcon color="action" aria-hidden />
                    </Stack>
                    <Typography variant="body2" sx={{ mt: 2 }}>
                      {i.documents} {i.documents === 1 ? "document" : "documenten"} · {i.sources.length}{" "}
                      {i.sources.length === 1 ? "bron" : "bronnen"} · bijgewerkt {formatDate(i.last_indexed_at)}
                    </Typography>
                    {i.sources.some((s) => !s.exists) && (
                      <Typography variant="body2" sx={{ mt: 1, color: "error.main" }}>Een bron bestaat niet (meer).</Typography>
                    )}
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
          </Box>
        )}

        {/* Shared by all indexes */}
        <Section
          title="Voor alle indexen"
          subtitle="Het embeddingmodel en de chunkgrootte gelden voor alle indexen. Een document dat in meerdere indexen zit, wordt één keer geëmbed."
        >
          {status && (
            <Stack direction="row" flexWrap="wrap" useFlexGap spacing={8}>
              <Fact label="Documenten" value={status.documents.toLocaleString("nl-NL")} />
              <Fact label="Chunks" value={status.chunks.toLocaleString("nl-NL")} />
              <Fact label="Afkortingen" value={status.abbreviations.toLocaleString("nl-NL")} />
              <Fact label="Laatst geïndexeerd" value={formatDate(status.last_indexed_at)} />
            </Stack>
          )}
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 6 }}>
            <Box>
              <Typography variant="overline" component="p">Embeddingmodel</Typography>
              <Typography sx={{ fontSize: 16, fontWeight: 600, color: "text.primary", overflowWrap: "anywhere" }}>{embedModel}</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                {reason
                  ? `Let op: ${reason}. Alle indexen worden opnieuw opgebouwd bij de volgende indexering. `
                  : "Vragen in de chat gebruiken automatisch hetzelfde model. "}
                <Link component={RouterLink} to="/instellingen">Wijzigen onder Instellingen</Link>
              </Typography>
            </Box>
            <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, pt: { md: "26px" }, flexWrap: "wrap" }}>
              {run.running ? (
                <Button variant="outlined" onClick={run.stop}>Stoppen</Button>
              ) : (
                <>
                  <Button
                    variant="outlined"
                    disabled={blockers.length > 0 || all.length === 0}
                    onClick={() => run.start(all, { embedModel, full: false })}
                  >
                    Alle indexen bijwerken
                  </Button>
                  <Button variant="outlined" color="error" disabled={blockers.length > 0 || all.length === 0} onClick={() => setConfirmFull(true)}>
                    Alles opnieuw…
                  </Button>
                </>
              )}
            </Box>
          </Box>
          {!run.running && blockers.length > 0 && (
            <Alert severity="info">
              <Typography sx={{ fontSize: 14, fontWeight: 600, color: "text.primary" }}>Nog nodig om te indexeren</Typography>
              <Box component="ul" sx={{ m: 0, mt: 1, pl: 5 }}>
                {blockers.map((b) => <li key={b}><Typography variant="body2">{b}</Typography></li>)}
              </Box>
            </Alert>
          )}
          <RunPanel run={run} />
          <Box>
            <Button variant="text" size="small" disabled={run.running || tokenState !== "ok"} onClick={rebuildAbbreviations}>
              Afkortingen opnieuw opbouwen
            </Button>
          </Box>
        </Section>

        {!tokenFirst && tokenCard}
      </Stack>

      <Dialog open={creating} onClose={() => setCreating(false)} maxWidth="xs" fullWidth>
        <Box component="form" onSubmit={(e) => { e.preventDefault(); create(); }}>
          <DialogTitle variant="h3">Nieuwe index</DialogTitle>
          <DialogContent>
            <TextField
              autoFocus
              label="Naam"
              placeholder="Mijn BV"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              error={createError !== null}
              helperText={createError ?? "Daarna kies je de mappen die erin horen."}
              fullWidth
              sx={{ mt: 2 }}
            />
          </DialogContent>
          <DialogActions sx={{ px: 6, pb: 6 }}>
            <Button variant="text" onClick={() => setCreating(false)}>Annuleren</Button>
            <Button type="submit" variant="contained" disabled={!newName.trim()}>Maken</Button>
          </DialogActions>
        </Box>
      </Dialog>

      <Dialog open={confirmFull} onClose={() => setConfirmFull(false)} maxWidth="xs" fullWidth>
        <DialogTitle variant="h3">Alles opnieuw opbouwen?</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            Alle {status?.documents ?? ""} geïndexeerde documenten worden verwijderd en voor alle {all.length} indexen
            opnieuw gelezen en geëmbed. Tot dat klaar is, vindt de chat minder. Indexen, bronnen en gesprekken blijven bewaard.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 6, pb: 6 }}>
          <Button variant="text" onClick={() => setConfirmFull(false)}>Annuleren</Button>
          <Button
            variant="outlined"
            color="error"
            onClick={() => {
              setConfirmFull(false);
              run.start(all, { embedModel, full: true });
            }}
          >
            Opnieuw opbouwen
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={toast !== null} autoHideDuration={2400} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: "bottom", horizontal: "center" }} />
    </Box>
  );
}
