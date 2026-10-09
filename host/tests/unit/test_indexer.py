"""The indexer's document payload and change detection, without Ollama or a NAS."""

from llama_index.core import Document

from indexing.change_detection import classify_documents, compute_hash
from indexing.indexer import IndexingConfig, document_payload


class FakeEmbedder:
    def __init__(self):
        self.inputs: list[str] = []

    def embed(self, texts):
        self.inputs.extend(texts)
        return [[float(len(t)), 1.0, 0.0] for t in texts]


def _doc(path: str, text: str) -> Document:
    doc = Document(text=text, metadata={"file_path": path, "file_name": path, "source_url": path})
    doc.metadata["content_hash"] = compute_hash(text)
    doc.excluded_embed_metadata_keys.append("content_hash")
    return doc


def test_payload_has_a_hierarchy_with_embedded_leaves():
    text = " ".join(f"Zin nummer {i} over het onderwerp." for i in range(600))
    config = IndexingConfig(parent_chunk_size=400, child_chunk_size=100)
    embedder = FakeEmbedder()

    payload = document_payload(_doc("wiki/a.md", text), config, embedder)

    nodes = {n["id"]: n for n in payload["nodes"]}
    leaves = [n for n in nodes.values() if n["is_leaf"]]
    parents = [n for n in nodes.values() if not n["is_leaf"]]
    assert parents and len(leaves) > len(parents)
    assert all(n["embedding"] is not None for n in leaves)
    assert all(n["embedding"] is None for n in parents)
    assert all(nodes[n["parent_id"]]["is_leaf"] is False for n in leaves)
    assert payload["content_hash"] == compute_hash(text)
    # The hash is excluded from what gets embedded; the file name is not.
    assert all("content_hash" not in t and "wiki/a.md" in t for t in embedder.inputs)


def test_classify():
    a, b = _doc("a", "one"), _doc("b", "two")
    indexed = {"a": compute_hash("one"), "b": "old", "gone": "x"}
    new, changed, deleted, unchanged = classify_documents([a, b, _doc("c", "three")], indexed)
    assert [d.metadata["file_path"] for d in new] == ["c"]
    assert [d.metadata["file_path"] for d in changed] == ["b"]
    assert deleted == ["gone"]
    assert unchanged == [a]
