// The indexing run, for the whole app: it keeps going when you leave the
// Indexen screens for the chat or the settings, and there is only ever one.
// The NAS holds the same rule across tabs, computers and the CLI (runIndexes
// takes a lock there). The embedding happens in this tab, so closing it stops
// the run; the next run picks up where it left off.
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { useAppState } from "./appState";
import { runIndexes, type LogLevel, type RunCounts, type RunProgress } from "./lib/indexer";

export interface RunResult {
  counts?: RunCounts;
  error?: string;
  stopped?: boolean;
}

export interface IndexRun {
  running: boolean;
  /** The indexes of the current or last run, e.g. "Mijn BV". */
  label: string | null;
  progress: RunProgress | null;
  log: { level: LogLevel; message: string }[];
  result: RunResult | null;
  /** Counts finished runs, so screens can reload their data after one. */
  finished: number;
  start: (indexes: { id: number; name: string }[], opts: { embedModel: string; full: boolean }) => Promise<void>;
  stop: () => void;
}

const Ctx = createContext<IndexRun | null>(null);

export function IndexRunProvider({ children }: { children: ReactNode }) {
  const { settings, refreshStatus, refreshIndexes } = useAppState();
  const [running, setRunning] = useState(false);
  const [label, setLabel] = useState<string | null>(null);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [log, setLog] = useState<IndexRun["log"]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [finished, setFinished] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  // Closing or reloading the tab mid-run would stop it: ask first.
  useEffect(() => {
    if (!running) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [running]);

  const start: IndexRun["start"] = async (indexes, { embedModel, full }) => {
    if (abortRef.current) return; // one run at a time
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setLabel(indexes.map((i) => i.name).join(", "));
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
      setFinished((n) => n + 1);
      refreshStatus();
      refreshIndexes();
    }
  };

  return (
    <Ctx.Provider value={{ running, label, progress, log, result, finished, start, stop: () => abortRef.current?.abort() }}>
      {children}
    </Ctx.Provider>
  );
}

/** The app's indexing run; onDone runs whenever a run ends while this screen is open. */
export function useIndexRun(onDone?: () => void): IndexRun {
  const run = useContext(Ctx);
  if (!run) throw new Error("useIndexRun outside IndexRunProvider");
  const seen = useRef(run.finished);
  useEffect(() => {
    if (run.finished !== seen.current) {
      seen.current = run.finished;
      onDone?.();
    }
  }, [run.finished]);
  return run;
}
