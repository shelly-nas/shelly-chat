"""Cross-process file lock for vector-db access.

An flock on `vector-db/.indexing.lock` serializes writers (the indexer, which
may run as an in-process background thread of the generating service or as a
standalone CLI process) against readers (the generating service re-reading
docstore.json after an indexing run). The in-process threading.Lock in
generating.indexing_runner stays separate: it gives concurrent HTTP triggers a
fast 409, while this flock guards actual file access across any combination of
processes — including the CLI path the threading.Lock cannot see.
"""

import fcntl
from contextlib import contextmanager
from pathlib import Path


def lock_path_for(docstore_path: str) -> Path:
    """Derive the lock file path from the docstore location."""
    return Path(docstore_path).parent / ".indexing.lock"


@contextmanager
def indexing_lock(lock_path: Path, exclusive: bool = True):
    """Hold an flock on lock_path for the duration of the with-block.

    exclusive=True (indexer/writer): blocks until all other holders release.
    exclusive=False (reader): multiple shared holders may coexist, but block
    while an exclusive holder is active.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()
