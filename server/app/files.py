"""The documents folder on the NAS, mounted read-only into the server.

Sources and document paths are relative to this folder (DOCUMENTS_ROOT inside
the container, DOCUMENTS_DIR on the NAS). Everything here refuses paths that
would leave it: absolute paths, '..', or symlinks pointing outside.
"""

from pathlib import Path, PurePosixPath

import pathspec

from app import config

SUPPORTED_EXTENSIONS = {".md", ".adoc", ".txt", ".pdf", ".docx", ".doc"}


class PathError(ValueError):
    pass


def root() -> Path:
    return Path(config.DOCUMENTS_ROOT).resolve()


def normalize(relative: str) -> str:
    """'/team//docs/' -> 'team/docs'; '' and '.' -> '' (the whole folder)."""
    text = relative.strip().replace("\\", "/")
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


def list_documents(source: str) -> list[str]:
    """Every supported file in a source (a folder, recursively, or one file)."""
    path = resolve(source)
    if path.is_file():
        return [relative(path)] if is_supported(path) else []
    if not path.is_dir():
        raise PathError(f"'{source or '.'}' bestaat niet in de documentenmap.")
    found = []
    for p in sorted(path.rglob("*")):
        # Skip hidden files and folders (.git, .DS_Store, @eaDir on Synology).
        rel_parts = p.relative_to(path).parts
        if any(part.startswith((".", "@")) for part in rel_parts):
            continue
        if is_supported(p):
            found.append(relative(p))
    return found


def browse(folder: str) -> dict:
    """Direct contents of a folder, to help pick a source."""
    path = resolve(folder)
    if not path.is_dir():
        raise PathError(f"'{folder or '.'}' is geen map in de documentenmap.")
    folders, documents = [], []
    for p in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if p.name.startswith((".", "@")):
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
