// The app's indexing run (see indexRun.tsx): progress, the result and a log.
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Alert, Box, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import type { IndexRun } from "../../indexRun";
import type { LogLevel } from "../../lib/indexer";

const LOG_ICON: Record<LogLevel, ReactNode> = {
  info: <InfoOutlinedIcon fontSize="small" color="action" aria-hidden />,
  success: <CheckCircleOutlineIcon fontSize="small" color="success" aria-hidden />,
  warning: <WarningAmberIcon fontSize="small" color="warning" aria-hidden />,
  error: <ErrorOutlineIcon fontSize="small" color="error" aria-hidden />,
};

export { useIndexRun } from "../../indexRun";

export default function RunPanel({ run }: { run: IndexRun }) {
  const { running, progress, result, log, label } = run;
  const percent = progress && progress.total ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <>
      {(running || progress) && (
        <Box>
          <Stack direction="row" justifyContent="space-between" sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ color: "text.primary" }} noWrap>
              {running
                ? `${label ? `${label}: ` : ""}${progress?.current ? `bezig met ${progress.current}…` : "documenten zoeken op de NAS…"}`
                : "Klaar"}
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
              <Chip size="small" label={`${progress.counts.deleted} uit de index`} />
              {progress.counts.failed > 0 && <Chip size="small" color="error" label={`${progress.counts.failed} mislukt`} />}
            </Stack>
          )}
          {running && (
            <Typography variant="caption" component="p" sx={{ mt: 2 }}>
              Je kunt intussen naar de chat of andere schermen; houd alleen dit tabblad open tot het klaar is. Stoppen
              is veilig: de volgende keer gaat het verder.
            </Typography>
          )}
        </Box>
      )}

      {result?.counts && (
        <Alert severity={result.counts.failed ? "warning" : "success"}>
          Indexering voltooid: {result.counts.new} nieuw, {result.counts.changed} gewijzigd,{" "}
          {result.counts.unchanged} ongewijzigd, {result.counts.deleted} uit de index gehaald
          {result.counts.failed ? `, ${result.counts.failed} mislukt (zie het logboek)` : ""}.
        </Alert>
      )}
      {result?.error && <Alert severity="error">Indexeren mislukt. {result.error}</Alert>}
      {result?.stopped && <Alert severity="info">Gestopt. Wat al opgeslagen was, blijft staan.</Alert>}

      {log.length > 0 && (
        <Box>
          <Typography variant="overline" component="h3">Logboek</Typography>
          <Stack spacing={1} sx={{ mt: 2, maxHeight: 280, overflowY: "auto", p: 3, borderRadius: 2, border: 1, borderColor: "divider" }}>
            {log.map((l, i) => (
              <Stack key={i} direction="row" spacing={2} alignItems="flex-start">
                {LOG_ICON[l.level]}
                <Typography variant="body2" sx={{ color: "text.primary", overflowWrap: "anywhere" }}>{l.message}</Typography>
              </Stack>
            ))}
          </Stack>
        </Box>
      )}
    </>
  );
}
