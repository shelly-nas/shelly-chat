"""The CLI indexer against fakes of the NAS and Ollama."""

import pytest

from indexing.indexer import IndexingConfig, reset_reason, run_pipeline

CHUNKS = {"parent_chunk_size": 1500, "child_chunk_size": 375, "parent_chunk_overlap": 300}
META = {"embed_model": "qwen3-embedding:latest", "embed_dimensions": 3, **CHUNKS}


class FakeNas:
    def __init__(self, indexes, meta=META):
        # indexes: {name: {"files": [...], "missing": [...]}}
        self.indexes_ = indexes
        self.meta = meta
        self.calls = []

    def indexes(self):
        return [{"id": n, "name": name} for n, name in enumerate(self.indexes_, 1)]

    def _name(self, index_id):
        return list(self.indexes_)[index_id - 1]

    def settings(self):
        return {"meta": self.meta, "chunk_config": CHUNKS, "embed_model": "qwen3-embedding:latest"}

    def put_meta(self, meta, reset):
        self.calls.append(("meta", meta["embed_model"], reset))

    def index_files(self, index_id):
        spec = self.indexes_[self._name(index_id)]
        return {"files": spec["files"], "missing": spec.get("missing", [])}

    def prepare_document(self, file_path, index_id):
        self.calls.append(("prepare", file_path, index_id))
        if file_path.startswith("same"):
            return {"status": "unchanged"}
        nodes = [
            {"id": "p", "parent_id": None, "is_leaf": False, "embed_text": None},
            {"id": "c", "parent_id": "p", "is_leaf": True, "embed_text": "embed me"},
        ]
        return {"status": "new", "document": {"file_path": file_path, "nodes": nodes}}

    def put_document(self, document):
        self.calls.append(("put", document["file_path"], document["index_id"], document["nodes"]))
        return {"chunks": len(document["nodes"]), "abbreviations": 0}

    def prune_index(self, index_id, keep):
        self.calls.append(("prune", index_id, keep))
        return {"removed": 1, "deleted_documents": 0}


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 2.0, 3.0] for _ in texts]

    def dimensions(self):
        return 3

    def unload(self):
        pass


def _run(monkeypatch, nas, **kwargs):
    monkeypatch.setattr(IndexingConfig, "nas", lambda self: nas)
    monkeypatch.setattr(IndexingConfig, "embedder", lambda self: FakeEmbedder())
    return run_pipeline(IndexingConfig(), **kwargs)


def test_indexes_every_index_and_prunes(monkeypatch):
    nas = FakeNas({"Mijn BV": {"files": ["same.md", "bv/new.md"]}, "Handboek": {"files": ["hb/a.md"]}})
    counts = _run(monkeypatch, nas)

    assert counts == {"new": 2, "changed": 0, "unchanged": 1, "deleted": 2, "failed": 0}
    assert ("meta", "qwen3-embedding:latest", False) in nas.calls
    put = next(c for c in nas.calls if c[0] == "put" and c[1] == "bv/new.md")
    assert put[2] == 1
    assert {n["id"]: n["embedding"] for n in put[3]} == {"p": None, "c": [1.0, 2.0, 3.0]}
    assert all("embed_text" not in n for n in put[3])
    assert ("prune", 1, ["same.md", "bv/new.md"]) in nas.calls
    assert ("prune", 2, ["hb/a.md"]) in nas.calls


def test_one_index_by_name(monkeypatch):
    nas = FakeNas({"Mijn BV": {"files": ["bv/a.md"]}, "Handboek": {"files": ["hb/a.md"]}})
    _run(monkeypatch, nas, only="handboek")
    assert [c[1] for c in nas.calls if c[0] == "prepare"] == ["hb/a.md"]
    with pytest.raises(SystemExit):
        _run(monkeypatch, nas, only="Bestaat niet")


def test_missing_source_never_prunes(monkeypatch):
    nas = FakeNas({"Mijn BV": {"files": [], "missing": ["bv"]}})
    counts = _run(monkeypatch, nas)
    assert counts["deleted"] == 0
    assert not any(c[0] == "prune" for c in nas.calls)


def test_reset_reason():
    meta = {"embed_model": "m", "embed_dimensions": 3, **CHUNKS}
    assert reset_reason(None, CHUNKS, "m", 3) is None
    assert reset_reason(meta, CHUNKS, "m", 3) is None
    assert "embeddingmodel" in reset_reason(meta, CHUNKS, "other", 3)
    assert "dimensie" in reset_reason(meta, CHUNKS, "m", 4)
    assert "parent_chunk_size" in reset_reason(meta, {**CHUNKS, "parent_chunk_size": 1}, "m", 3)
