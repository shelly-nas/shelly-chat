// An indexing run: starting, stopping, progress, the result and a log.
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Alert, Box, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useAppState } from "../../appState";
import { runIndexes, type LogLevel, type RunCounts, type RunProgress } from "../../lib/indexer";

const LOG_ICON: Record<LogLevel, ReactNode> = {
  info: <InfoOutlinedIcon fontSize="small" color="action" aria-hidden />,
  success: <CheckCircleOutlineIcon fontSize="small" color="success" aria-hidden />,
  warning: <WarningAmberIcon fontSize="small" color="warning" aria-hidden />,
  error: <ErrorOutlineIcon fontSize="small" color="error" aria-hidden />,
};

interface Result {
  counts?: RunCounts;
  error?: string;
  stopped?: boolean;
}

export interface IndexRun {
  running: boolean;
  progress: RunProgress | null;
  log: { level: LogLevel; message: string }[];
  result: Result | null;
  start: (indexes: { id: number; name: string }[], opts: { embedModel: string; full: boolean }) => Promise<void>;
  stop: () => void;
}

/** State of one indexing run; refreshes the app's index data when it ends. */
export function useIndexRun(onDone?: () => void): IndexRun {
  const { settings, refreshStatus, refreshIndexes } = useAppState();
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [log, setLog] = useState<IndexRun["log"]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Leaving the page mid-run would stop it: ask first.
  useEffect(() => {
    if (!running) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [running]);

  const start: IndexRun["start"] = async (indexes, { embedModel, full }) => {
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setResult(null);
    setLog([]);
    setProgress(null);
    try {
      const counts = await runIndexes(
        {
          ollamaUrl: settings.ollamaUrl,
          embedModel,
          indexToken: settings.indexToken,
          full,
          signal: controller.signal,
          log: (level, message) => setLog((prev) => [...prev.slice(-299), { level, message }]),
          progress: setProgress,
        },
        indexes,
      );
      setResult({ counts });
    } catch (err) {
      setResult(controller.signal.aborted ? { stopped: true } : { error: (err as Error).message });
    } finally {
      setRunning(false);
      abortRef.current = null;
      refreshStatus();
      refreshIndexes();
      onDone?.();
    }
  };

  return { running, progress, log, result, start, stop: () => abortRef.current?.abort() };
}

export default function RunPanel({ run }: { run: IndexRun }) {
  const { running, progress, result, log } = run;
  const percent = progress && progress.total ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <>
      {(running || progress) && (
        <Box>
          <Stack direction="row" justifyContent="space-between" sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ color: "text.primary" }} noWrap>
              {running ? (progress?.current ? `Bezig met ${progress.current}…` : "Documenten zoeken op de NAS…") : "Klaar"}
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
              Houd dit tabblad open tot het klaar is. Stoppen is veilig: de volgende keer gaat het verder.
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
