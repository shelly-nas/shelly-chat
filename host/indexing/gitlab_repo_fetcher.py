"""GitLab repository fetcher.

Downloads supported documents (.md, .adoc, .pdf, .docx, .doc) from a GitLab
repository via the REST API and returns them as Documents with the file's bytes (base64) for the NAS to extract.
Each document carries a ``source_url`` metadata field pointing to the
original file in GitLab (``/-/blob/<branch>/<path>`` format).
"""

import re
import time
from typing import List, Optional

import requests

from indexing.console import log_info, log_warn
from indexing.source_document import Document

_SUPPORTED_EXTS = frozenset({".md", ".adoc", ".pdf", ".docx", ".doc"})


def _parse_repo_url(repo_url: str):
    """Return (base_url, project_path, branch, path_filter) from a GitLab repo URL.

    Handles plain repo URLs as well as tree URLs of the form:
    ``https://gitlab.example.com/group/project/-/tree/<branch>/<path>``
    Query parameters such as ``?ref_type=heads`` are ignored.
    """
    url = repo_url.rstrip("/").split("?")[0]

    tree_match = re.search(r"/-/tree/([^/]+)(?:/(.+))?$", url)
    if tree_match:
        branch = tree_match.group(1)
        path_filter = tree_match.group(2) or None
        base_part = url[: tree_match.start()]
    else:
        branch = None
        path_filter = None
        base_part = re.sub(r"/-/(tree|blob).*$", "", url)

    match = re.match(r"(https?://[^/]+)/(.+)$", base_part)
    if not match:
        raise ValueError(f"Cannot parse GitLab repo URL: {repo_url}")
    return match.group(1), match.group(2).rstrip("/"), branch, path_filter


def _file_ext(path: str) -> str:
    """Return the lowercase file extension including the leading dot."""
    if "." not in path.rsplit("/", 1)[-1]:
        return ""
    return "." + path.rsplit(".", 1)[-1].lower()


def fetch_repo_documents(
    repo_url: str,
    token: Optional[str] = None,
    path_filter: Optional[str] = None,
    branch: Optional[str] = None,
    request_timeout: int = 30,
    rate_limit_delay: float = 0.1,
) -> List[Document]:
    """Fetch supported documents from a GitLab repository.

    Supported extensions: ``.md``, ``.adoc``, ``.pdf``, ``.docx``, ``.doc``

    Args:
        repo_url: Full GitLab repository URL.
        token: Personal Access Token with ``read_repository`` scope.
        path_filter: Optional subdirectory to limit the search (e.g. ``docs/``).
        branch: Branch or tag to read from. Defaults to the repository's
            default branch.
        request_timeout: HTTP timeout in seconds.
        rate_limit_delay: Seconds to wait between API requests.

    Raises:
        PermissionError: When the PAT is missing or lacks permissions.
        ValueError: When the repository URL cannot be resolved.
        ConnectionError: On network or API errors.
    """
    base_url, project_path, url_branch, url_path = _parse_repo_url(repo_url)
    if branch is None:
        branch = url_branch
    if path_filter is None:
        path_filter = url_path

    encoded_path = requests.utils.quote(project_path, safe="")
    api_base = f"{base_url}/api/v4/projects/{encoded_path}"
    headers = {"PRIVATE-TOKEN": token} if token else {}

    # Resolve default branch when not provided.
    if not branch:
        try:
            resp = requests.get(api_base, headers=headers, timeout=request_timeout)
            if resp.status_code == 401:
                raise PermissionError("GitLab API: Unauthorized. Check GITLAB_PAT.")
            if resp.status_code == 403:
                raise PermissionError(
                    "GitLab API: Forbidden. PAT needs read_repository permission."
                )
            if resp.status_code == 404:
                raise ValueError(f"GitLab repository not found: {repo_url}")
            resp.raise_for_status()
            branch = resp.json().get("default_branch", "main")
        except requests.RequestException as exc:
            raise ConnectionError(f"Could not fetch project info: {exc}") from exc

    log_info(
        f"Fetching repository files from {base_url}/{project_path} (branch: {branch}) ..."
    )

    # List all files recursively via the repository tree API.
    all_blob_paths: List[str] = []
    page = 1
    per_page = 100

    while True:
        params: dict = {"recursive": True, "per_page": per_page, "page": page, "ref": branch}
        if path_filter:
            params["path"] = path_filter.rstrip("/")

        try:
            resp = requests.get(
                f"{api_base}/repository/tree",
                headers=headers,
                params=params,
                timeout=request_timeout,
            )
        except requests.RequestException as exc:
            raise ConnectionError(f"GitLab API request failed: {exc}") from exc

        if resp.status_code == 401:
            raise PermissionError("GitLab API: Unauthorized. Check GITLAB_PAT.")
        if resp.status_code == 403:
            raise PermissionError(
                "GitLab API: Forbidden. PAT needs read_repository permission."
            )
        if resp.status_code == 404:
            raise ValueError(f"GitLab repository not found: {repo_url}")
        resp.raise_for_status()

        items = resp.json()
        if not items:
            break

        for item in items:
            if item.get("type") == "blob":
                all_blob_paths.append(item["path"])

        total_pages = int(resp.headers.get("X-Total-Pages", 1))
        if page >= total_pages:
            break
        page += 1

    # Keep only files with a supported extension; everything else is ignored.
    to_fetch: List[tuple] = [
        (file_path, _file_ext(file_path))
        for file_path in all_blob_paths
        if _file_ext(file_path) in _SUPPORTED_EXTS
    ]

    log_info(
        f"Found {len(to_fetch)} supported file(s) "
        f"({len(all_blob_paths)} total, "
        f"{len(all_blob_paths) - len(to_fetch)} skipped)"
    )

    documents: List[Document] = []
    for file_path, ext in to_fetch:
        encoded_file = requests.utils.quote(file_path, safe="")
        try:
            resp = requests.get(
                f"{api_base}/repository/files/{encoded_file}",
                headers=headers,
                params={"ref": branch},
                timeout=request_timeout,
            )
            if resp.status_code == 404:
                log_warn(f"File not found (deleted?): {file_path}")
                continue
            resp.raise_for_status()
        except requests.RequestException as exc:
            log_warn(f"Failed to fetch {file_path}: {exc}")
            continue

        # The NAS extracts the text (Markdown, PDF, DOCX), the same way for
        # documents indexed from the app, so both get identical chunks.
        file_data = resp.json()

        source_url = f"{base_url}/{project_path}/-/blob/{branch}/{file_path}"
        doc = Document(
            data_base64=file_data.get("content", ""),
            metadata={
                "source_url": source_url,
                "file_name": file_path.split("/")[-1],
                "file_path": source_url,
                "repo_project": project_path,
                "repo_branch": branch,
                "repo_file_path": file_path,
            },
        )
        documents.append(doc)
        log_info(f"  Fetched: {file_path}")
        time.sleep(rate_limit_delay)

    log_info(f"Fetched {len(documents)} document(s) from {base_url}/{project_path}")
    return documents
