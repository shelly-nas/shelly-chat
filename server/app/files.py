"""The documents folder on the NAS, mounted read-only into the server.

Sources and document paths are stored relative to this folder (DOCUMENTS_ROOT
inside the container, DOCUMENTS_DIR on the NAS). On the NAS that is '/', the
whole file system, so 'home/Jelle/Documenten' is /home/Jelle/Documenten there.
An absolute path as the NAS sees it is accepted too, as long as it lies in
DOCUMENTS_DIR. Everything here refuses paths that would leave the folder:
'..', absolute paths outside DOCUMENTS_DIR, or symlinks pointing outside.
"""

import os
from pathlib import Path, PurePosixPath

import pathspec

from app import config

SUPPORTED_EXTENSIONS = {".md", ".adoc", ".txt", ".pdf", ".docx", ".doc"}

# With the whole file system mounted: never walk the kernel's and the
# system's own folders. They hold no documents and /proc never ends.
SYSTEM_FOLDERS = {"proc", "sys", "dev", "run", "tmp", "lost+found"}


class PathError(ValueError):
    pass


def root() -> Path:
    return Path(config.DOCUMENTS_ROOT).resolve()


def _documents_dir() -> PurePosixPath | None:
    """DOCUMENTS_DIR when it is an absolute path on the NAS, else None (local ./documents)."""
    configured = config.DOCUMENTS_DIR.strip()
    return PurePosixPath(configured) if configured.startswith("/") else None


def is_whole_file_system() -> bool:
    return _documents_dir() == PurePosixPath("/")


def normalize(relative: str) -> str:
    """'team//docs/' -> 'team/docs'; '' and '.' -> '' (the whole folder).

    An absolute path is taken as the NAS sees it: with DOCUMENTS_DIR=/volume1/docs,
    '/volume1/docs/team' -> 'team'. Without an absolute DOCUMENTS_DIR a leading
    '/' only means the documents folder itself.
    """
    text = relative.strip().replace("\\", "/")
    base = _documents_dir()
    if text.startswith("/") and base is not None:
        try:
            text = PurePosixPath(text).relative_to(base).as_posix()
        except ValueError:
            raise PathError(f"{text} ligt buiten de documentenmap {base}.") from None
    parts = [p for p in PurePosixPath(text).parts if p not in ("/", ".", "")]
    if any(p == ".." for p in parts):
        raise PathError("Een pad mag niet met '..' buiten de documentenmap komen.")
    return "/".join(parts)


def resolve(relative: str) -> Path:
    """The real path for a relative path, guaranteed inside the documents folder."""
    base = root()
    path = (base / normalize(relative)).resolve()
    if path != base and base not in path.parents:
        raise PathError("Dit pad ligt buiten de documentenmap.")
    return path


def is_supported(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and not path.name.startswith(".")


def relative(path: Path) -> str:
    return path.relative_to(root()).as_posix()


def _skipped(name: str, parent: Path) -> bool:
    """Hidden (.git, .DS_Store), Synology's own (@eaDir, @docker), or a system folder at the top."""
    return name.startswith((".", "@")) or (parent == root() and name in SYSTEM_FOLDERS)


def list_documents(source: str) -> list[str]:
    """Every supported file in a source (a folder, recursively, or one file)."""
    if normalize(source) == "" and is_whole_file_system():
        raise PathError("De hele NAS als bron is te veel; kies een map.")
    path = resolve(source)
    if path.is_file():
        return [relative(path)] if is_supported(path) else []
    if not path.is_dir():
        raise PathError(f"'{source or '.'}' bestaat niet in de documentenmap.")
    found = []
    # os.walk prunes skipped folders instead of descending into them, and does
    # not follow symlinked folders, so a large tree stays a single pass.
    for dirpath, dirnames, filenames in os.walk(path):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not _skipped(d, here)]
        for name in filenames:
            p = here / name
            if not _skipped(name, here) and is_supported(p):
                found.append(relative(p))
    return sorted(found)


def browse(folder: str) -> dict:
    """Direct contents of a folder, to help pick a source."""
    path = resolve(folder)
    if not path.is_dir():
        raise PathError(f"'{folder or '.'}' is geen map in de documentenmap.")
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        raise PathError(f"De server mag '{folder}' niet lezen.") from None
    folders, documents = [], []
    for p in entries:
        if _skipped(p.name, path):
            continue
        if p.is_dir():
            folders.append(relative(p))
        elif is_supported(p):
            documents.append(relative(p))
    return {"path": normalize(folder), "folders": folders, "documents": documents}


def ignore_spec(patterns: str) -> pathspec.GitIgnoreSpec:
    """gitignore semantics, matched against paths relative to the documents folder."""
    return pathspec.GitIgnoreSpec.from_lines(patterns.splitlines())


def list_index_documents(sources: list[str], ignore_patterns: str) -> tuple[list[str], list[str]]:
    """Every document in an index's sources, minus what the ignore patterns exclude.

    Returns (files, missing): `missing` are sources that could not be read. A
    run only removes documents that are gone when nothing is missing, so a
    folder that is (temporarily) unavailable never empties an index.
    """
    spec = ignore_spec(ignore_patterns)
    found: dict[str, None] = {}
    missing = []
    for source in sources:
        try:
            for path in list_documents(source):
                if not spec.match_file(path):
                    found[path] = None
        except PathError:
            missing.append(source)
    return sorted(found), missing
