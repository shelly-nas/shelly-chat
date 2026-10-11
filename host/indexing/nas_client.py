"""Client for the index endpoints of the shelly-chat server on the NAS."""

from typing import Dict, Optional

import requests


class NasError(RuntimeError):
    pass


class NasClient:
    def __init__(self, base_url: str, token: str = "", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.ConnectionError as exc:
            raise NasError(f"Kan {self.base_url} niet bereiken: {exc}") from exc
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise NasError(f"{method} {path} gaf {resp.status_code}: {detail}")
        return resp.json() if resp.content else None

    def status(self) -> dict:
        return self._request("GET", "/api/index")

    def settings(self) -> dict:
        """Chunk configuration, sources and the current index meta."""
        return self._request("GET", "/api/index/settings")

    def list_files(self) -> dict:
        """Documents in the sources (`files`) and sources that could not be read (`missing`)."""
        return self._request("GET", "/api/index/files")

    def prepare_document(self, file_path: str) -> dict:
        return self._request("POST", "/api/index/prepare", json={"file_path": file_path})

    def put_meta(self, meta: dict, reset: bool) -> dict:
        return self._request("PUT", "/api/index/meta", json={**meta, "reset": reset})

    def indexed_hashes(self) -> Dict[str, str]:
        docs = self._request("GET", "/api/index/documents")["documents"]
        return {d["file_path"]: d["content_hash"] for d in docs}

    def put_document(self, document: dict) -> dict:
        return self._request("PUT", "/api/index/documents", json=document)

    def delete_document(self, file_path: str) -> None:
        self._request("DELETE", "/api/index/documents", params={"file_path": file_path})

    def rebuild_abbreviations(self) -> dict:
        return self._request("POST", "/api/index/abbreviations")

    def current_meta(self) -> Optional[dict]:
        return self.status().get("meta")
