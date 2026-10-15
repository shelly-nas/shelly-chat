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

    def lease_run(self, run_id: str, label: str) -> dict:
        """Take or renew the one-run-at-a-time lock; NasError (409) while another run has it."""
        return self._request("PUT", "/api/index/run", json={"run_id": run_id, "label": label})

    def end_run(self, run_id: str) -> None:
        self._request("DELETE", f"/api/index/run/{run_id}")

    def status(self) -> dict:
        return self._request("GET", "/api/index")

    def settings(self) -> dict:
        """Chunk configuration, sources and the current index meta."""
        return self._request("GET", "/api/index/settings")

    def indexes(self) -> list:
        return self._request("GET", "/api/indexes")["indexes"]

    def index_files(self, index_id: int) -> dict:
        """Documents in the index (`files`) and sources that could not be read (`missing`)."""
        return self._request("GET", f"/api/indexes/{index_id}/files")

    def prepare_document(self, file_path: str, index_id: int, descriptions: Optional[dict] = None) -> dict:
        body = {"file_path": file_path, "index_id": index_id}
        if descriptions is not None:
            body["descriptions"] = descriptions
        return self._request("POST", "/api/index/prepare", json=body)

    def visual(self, file_path: str, visual_id: str) -> str:
        """A page or image of a document as base64 PNG, for the vision model."""
        return self._request("GET", "/api/index/visual", params={"file_path": file_path, "id": visual_id})["image"]

    def prune_index(self, index_id: int, keep: list) -> dict:
        return self._request("POST", f"/api/indexes/{index_id}/prune", json={"keep": keep})

    def put_meta(self, meta: dict, reset: bool) -> dict:
        return self._request("PUT", "/api/index/meta", json={**meta, "reset": reset})

    def indexed_hashes(self) -> Dict[str, str]:
        docs = self._request("GET", "/api/index/documents")["documents"]
        return {d["file_path"]: d["content_hash"] for d in docs}

    def put_document(self, document: dict) -> dict:
        return self._request("PUT", "/api/index/documents", json=document)

    def rebuild_abbreviations(self) -> dict:
        return self._request("POST", "/api/index/abbreviations")

    def current_meta(self) -> Optional[dict]:
        return self.status().get("meta")
