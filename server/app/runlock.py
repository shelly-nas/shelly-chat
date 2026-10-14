"""One indexing run at a time.

Indexing embeds with Ollama on the machine that runs it; two runs at once
(two tabs, two computers, the app and the CLI) would compete for the same
memory and the same documents. A run takes this lock before it starts and
renews it while it works (the browser every 30 seconds). A run that stops
renewing - a closed tab, a crashed CLI - loses it after LEASE_SECONDS.

Kept in memory: the server runs as a single process, and a restart ending
every lease is fine, since the runs themselves stop with it.
"""

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

LEASE_SECONDS = 180


@dataclass
class Run:
    id: str
    label: str
    started_at: datetime
    renewed: float  # time.monotonic()

    def public(self) -> dict:
        return {"id": self.id, "label": self.label, "started_at": self.started_at.isoformat()}


class Busy(Exception):
    def __init__(self, run: Run):
        super().__init__(run.label)
        self.run = run


_lock = threading.Lock()
_current: Run | None = None


def _live() -> Run | None:
    global _current
    if _current and time.monotonic() - _current.renewed > LEASE_SECONDS:
        _current = None
    return _current


def current() -> Run | None:
    with _lock:
        return _live()


def acquire(run_id: str, label: str) -> Run:
    """Take the lock for run_id, or renew it if run_id already has it; Busy otherwise."""
    global _current
    with _lock:
        run = _live()
        if run and run.id != run_id:
            raise Busy(run)
        if run:
            run.renewed = time.monotonic()
        else:
            run = _current = Run(run_id, label, datetime.now(timezone.utc), time.monotonic())
        return run


def release(run_id: str) -> None:
    global _current
    with _lock:
        if _current and _current.id == run_id:
            _current = None
