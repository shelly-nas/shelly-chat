"""GitLab wiki fetcher.

Retrieves all markdown pages from a GitLab wiki via the REST API and returns
them as Documents. Each document carries a ``source_url``
metadata field pointing to the original GitLab wiki page.

Supported input URL formats:
  https://gitlab.example.com/group/project/-/wikis
  https://gitlab.example.com/group/project/-/wikis/home
  https://gitlab.example.com/group/project
"""

import re
import time
from typing import List, Optional

import requests

from indexing.console import log_info, log_warn
from indexing.source_document import Document


def _parse_wiki_url(wiki_url: str):
    """Return (base_url, project_path) extracted from a GitLab wiki URL."""
    url = wiki_url.rstrip("/")
    url = re.sub(r"/-/wikis.*$", "", url)
    match = re.match(r"(https?://[^/]+)/(.+)$", url)
    if not match:
        raise ValueError(f"Cannot parse GitLab wiki URL: {wiki_url}")
    return match.group(1), match.group(2).rstrip("/")


def fetch_wiki_documents(
    wiki_url: str,
    token: Optional[str] = None,
    request_timeout: int = 30,
    rate_limit_delay: float = 0.1,
) -> List[Document]:
    """Fetch all markdown wiki pages from a GitLab wiki.

    Authentication is via a Personal Access Token (PAT) with ``read_wiki``
    scope. Public wikis can be accessed without a token.

    Raises:
        PermissionError: When the PAT is missing or lacks permissions.
        ValueError: When the wiki URL cannot be resolved.
        ConnectionError: On network or API errors.
    """
    base_url, project_path = _parse_wiki_url(wiki_url)
    encoded_path = requests.utils.quote(project_path, safe="")
    api_base = f"{base_url}/api/v4/projects/{encoded_path}"
    headers = {"PRIVATE-TOKEN": token} if token else {}

    log_info(f"Fetching wiki pages from {base_url}/{project_path} ...")

    documents: List[Document] = []
    page = 1
    per_page = 100

    while True:
        try:
            resp = requests.get(
                f"{api_base}/wikis",
                headers=headers,
                params={"page": page, "per_page": per_page, "with_content": 1},
                timeout=request_timeout,
            )
        except requests.RequestException as exc:
            raise ConnectionError(f"GitLab API request failed: {exc}") from exc

        if resp.status_code == 401:
            raise PermissionError("GitLab API: Unauthorized. Check GITLAB_PAT.")
        if resp.status_code == 403:
            raise PermissionError(
                "GitLab API: Forbidden. PAT needs read_wiki permission."
            )
        if resp.status_code == 404:
            raise ValueError(f"GitLab wiki not found: {wiki_url}")
        resp.raise_for_status()

        pages = resp.json()
        if not pages:
            break

        for wiki_page in pages:
            slug = wiki_page.get("slug", "")
            title = wiki_page.get("title", slug)
            content = wiki_page.get("content", "")
            fmt = wiki_page.get("format", "markdown")

            if fmt not in ("markdown", "md"):
                log_warn(
                    f"Skipping wiki page '{title}' (format: {fmt}, only markdown supported)"
                )
                continue

            if not content.strip():
                log_warn(f"Skipping empty wiki page '{title}'")
                continue

            source_url = f"{base_url}/{project_path}/-/wikis/{slug}"
            doc = Document(
                text=content,
                metadata={
                    "source_url": source_url,
                    "file_name": f"{slug}.md",
                    "file_path": source_url,
                    "wiki_project": project_path,
                    "wiki_slug": slug,
                    "title": title,
                },
            )
            documents.append(doc)
            log_info(f"  Fetched wiki page: {title}")
            time.sleep(rate_limit_delay)

        total_pages = int(resp.headers.get("X-Total-Pages", 1))
        if page >= total_pages:
            break
        page += 1

    log_info(f"Fetched {len(documents)} wiki page(s) from {base_url}/{project_path}")
    return documents
