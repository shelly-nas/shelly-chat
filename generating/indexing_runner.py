"""Background indexing runner for the generating service.

Wraps run_indexing_pipeline in a threading.Thread so the FastAPI event loop
is never blocked. Captures stdout (print) output from the indexer by
temporarily redirecting sys.stdout while the run is active.
"""

import io
import logging
import os
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from indexing.indexer import run_indexing_pipeline

logger = logging.getLogger(__name__)

_MAX_LOG_LINES = 50
_DATA_DIR = os.getenv("DATA_DIR", "/app/data")

_lock = threading.Lock()

_state: dict = {
    "status": "idle",       # idle | running | done | error
    "message": "",
    "logs": [],
    "started_at": None,
    "finished_at": None,
    "progress_current": 0,
    "progress_total": 0,
}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def set_progress(current: int, total: int) -> None:
    with _lock:
        _state["progress_current"] = current
        _state["progress_total"] = total


def start_indexing(
    full_reindex: bool = False,
    build_abbreviations: bool = False,
    on_complete: Optional[Callable[[], None]] = None,
) -> None:
    """Start indexing in a background thread.

    Raises RuntimeError if a run is already in progress — the caller is
    responsible for translating this to HTTP 409.

    *on_complete* is called after a successful run (e.g. to reload retrieval
    state). Errors from the callback are logged but do not change the run
    status to 'error'.
    """
    with _lock:
        if _state["status"] == "running":
            raise RuntimeError("Indexing already running")
        _state.update({
            "status": "running",
            "message": "Indexering gestart...",
            "logs": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "progress_current": 0,
            "progress_total": 0,
        })

    t = threading.Thread(target=_run, args=(full_reindex, build_abbreviations, on_complete), daemon=True)
    t.start()


def _append_log(line: str) -> None:
    # Strip ANSI colour codes before storing
    import re
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
    if not clean:
        return
    with _lock:
        _state["logs"].append(clean)
        if len(_state["logs"]) > _MAX_LOG_LINES:
            _state["logs"] = _state["logs"][-_MAX_LOG_LINES:]
        _state["message"] = clean


class _CapturingStream(io.TextIOBase):
    """Write to both real stdout and the log buffer."""

    def __init__(self, real: io.TextIOBase):
        self._real = real

    def write(self, s: str) -> int:
        self._real.write(s)
        self._real.flush()
        for line in s.splitlines():
            _append_log(line)
        return len(s)

    def flush(self) -> None:
        self._real.flush()


def _run(
    full_reindex: bool = False,
    build_abbreviations: bool = False,
    on_complete: Optional[Callable[[], None]] = None,
) -> None:
    real_stdout = sys.stdout
    sys.stdout = _CapturingStream(real_stdout)
    try:
        data_dir = Path(_DATA_DIR)
        data_dir.mkdir(parents=True, exist_ok=True)
        run_indexing_pipeline(str(data_dir), full_reindex=full_reindex, build_abbreviations=build_abbreviations)
        if on_complete is not None:
            try:
                on_complete()
            except Exception as exc:
                logger.error("on_complete callback failed after indexing: %s", exc)
        with _lock:
            _state["status"] = "done"
            _state["message"] = "Indexering voltooid."
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        with _lock:
            _state["status"] = "error"
            _state["message"] = str(exc)
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        _append_log(f"[ERROR] {exc}")
    finally:
        sys.stdout = real_stdout
