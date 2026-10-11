"""The CLI indexer against fakes of the NAS and Ollama."""

from indexing.indexer import IndexingConfig, reset_reason, run_pipeline

CHUNKS = {"parent_chunk_size": 1500, "child_chunk_size": 375, "parent_chunk_overlap": 300}


class FakeNas:
    def __init__(self, meta=None, indexed=None, files=(), missing=()):
        self.meta = meta
        self.indexed = indexed or {}
        self.files = list(files)
        self.missing = list(missing)
        self.calls = []

    def settings(self):
        return {"meta": self.meta, "chunk_config": CHUNKS, "sources": [{"path": "handboek"}]}

    def list_files(self):
        return {"files": self.files, "missing": self.missing}

    def put_meta(self, meta, reset):
        self.calls.append(("meta", meta["embed_model"], reset))

    def indexed_hashes(self):
        return self.indexed

    def prepare_document(self, file_path):
        if file_path == "a":
            return {"status": "unchanged"}
        nodes = [
            {"id": "p", "parent_id": None, "is_leaf": False, "embed_text": None},
            {"id": "c", "parent_id": "p", "is_leaf": True, "embed_text": "embed me"},
        ]
        return {"status": "new", "document": {"file_path": file_path, "nodes": nodes}}

    def put_document(self, document):
        self.calls.append(("put", document["file_path"], document["nodes"]))
        return {"chunks": len(document["nodes"]), "abbreviations": 0}

    def delete_document(self, path):
        self.calls.append(("delete", path))


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 2.0, 3.0] for _ in texts]

    def dimensions(self):
        return 3

    def unload(self):
        pass


def _run(monkeypatch, nas):
    monkeypatch.setattr(IndexingConfig, "nas", lambda self: nas)
    monkeypatch.setattr(IndexingConfig, "embedder", lambda self: FakeEmbedder())
    return run_pipeline(IndexingConfig())


def test_embeds_new_skips_unchanged_and_removes_gone(monkeypatch):
    meta = {"embed_model": "qwen3-embedding:latest", "embed_dimensions": 3, **CHUNKS}
    nas = FakeNas(meta=meta, indexed={"a": "h", "gone": "h"}, files=["a", "b"])
    counts = _run(monkeypatch, nas)

    assert counts == {"new": 1, "changed": 0, "unchanged": 1, "deleted": 1, "failed": 0}
    assert ("meta", "qwen3-embedding:latest", False) in nas.calls
    put = next(c for c in nas.calls if c[0] == "put")
    assert put[1] == "b"
    assert {n["id"]: n["embedding"] for n in put[2]} == {"p": None, "c": [1.0, 2.0, 3.0]}
    assert all("embed_text" not in n for n in put[2])
    assert ("delete", "gone") in nas.calls


def test_missing_source_never_deletes(monkeypatch):
    meta = {"embed_model": "qwen3-embedding:latest", "embed_dimensions": 3, **CHUNKS}
    nas = FakeNas(meta=meta, indexed={"a": "h"}, files=[], missing=["handboek"])
    counts = _run(monkeypatch, nas)
    assert counts["deleted"] == 0
    assert not any(c[0] == "delete" for c in nas.calls)


def test_reset_reason():
    meta = {"embed_model": "m", "embed_dimensions": 3, **CHUNKS}
    assert reset_reason(None, CHUNKS, "m", 3) is None
    assert reset_reason(meta, CHUNKS, "m", 3) is None
    assert "embeddingmodel" in reset_reason(meta, CHUNKS, "other", 3)
    assert "dimensie" in reset_reason(meta, CHUNKS, "m", 4)
    assert "parent_chunk_size" in reset_reason(meta, {**CHUNKS, "parent_chunk_size": 1}, "m", 3)
