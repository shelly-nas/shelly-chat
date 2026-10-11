"""End-to-end over the HTTP API against a real Postgres with pgvector.

Needs the DB_* variables (CI sets them; locally: a database started from
database/ with init.sql applied). Skipped without DB_HOST.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DB_HOST"), reason="needs a database (DB_HOST)")

TOKEN = "test-token"


@pytest.fixture(scope="module")
def docs_root(tmp_path_factory):
    """A documents folder like the one mounted on the NAS."""
    import docx

    root = tmp_path_factory.mktemp("documents")
    (root / "handboek").mkdir()
    (root / "handboek" / "brp.md").write_text(
        " ".join(f"Zin {i} over de Basisregistratie Personen (BRP)." for i in range(400))
    )
    (root / "handboek" / "notities.xyz").write_text("niet ondersteund")
    (root / "handboek" / ".verborgen.md").write_text("verborgen")
    (root / "team").mkdir()
    d = docx.Document()
    d.add_paragraph("Het Renovate-proces opent pull requests.")
    d.save(root / "team" / "renovate.docx")
    (root / "geheim.md").write_text("los bestand in de root")
    return root


@pytest.fixture(scope="module")
def client(docs_root):
    os.environ["INDEX_TOKEN"] = TOKEN
    from app import config

    config.INDEX_TOKEN = TOKEN
    config.DOCUMENTS_ROOT = str(docs_root)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": f"Bearer {TOKEN}"}
META = {"embed_model": "test-embed", "embed_dimensions": 3}


def _document(path: str, leaves: list[tuple[str, list[float]]]) -> dict:
    parent = f"{path}-p"
    return {
        "file_path": path,
        "file_name": path.rsplit("/", 1)[-1],
        "source_url": f"/api/files/{path}",
        "content_hash": "hash-" + path,
        "content": "De Basisregistratie Personen (BRP) is de bron. " + " ".join(t for t, _ in leaves),
        "nodes": [
            {"id": parent, "is_leaf": False, "position": 0, "content": "parent of " + path},
            *[
                {
                    "id": f"{path}-{i}",
                    "parent_id": parent,
                    "is_leaf": True,
                    "position": i + 1,
                    "content": text,
                    "embedding": emb,
                }
                for i, (text, emb) in enumerate(leaves)
            ],
        ],
    }


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "version" in body


def test_index_requires_token(client):
    assert client.put("/api/index/meta", json=META).status_code == 401


def test_index_and_retrieve(client):
    r = client.put("/api/index/meta", json={**META, "reset": True}, headers=AUTH)
    assert r.status_code == 200, r.text

    # Changing the config without reset is refused.
    r = client.put("/api/index/meta", json={**META, "embed_model": "other"}, headers=AUTH)
    assert r.status_code == 409
    # The chunk configuration comes from the server, not from the indexer.
    assert r.json() and client.get("/api/index/settings").json()["meta"]["parent_chunk_size"] == 1500

    docs = [
        _document("wiki/a.md", [("alpha one", [1, 0, 0]), ("alpha two", [0.9, 0.1, 0]), ("alpha three", [0, 0, 1])]),
        _document("wiki/b.md", [("beta one", [0, 1, 0]), ("beta two", [0.1, 0.9, 0]), ("beta three", [0, 0.8, 0.2]), ("beta four", [0, 0, 1])]),
    ]
    for d in docs:
        r = client.put("/api/index/documents", json=d, headers=AUTH)
        assert r.status_code == 200, r.text
    assert r.json()["abbreviations"] == 1

    listed = client.get("/api/index/documents", headers=AUTH).json()["documents"]
    assert [d["file_path"] for d in listed] == ["wiki/a.md", "wiki/b.md"]

    # A wrong dimension count is refused before anything is stored.
    bad = _document("wiki/c.md", [("x", [1, 0])])
    assert client.put("/api/index/documents", json=bad, headers=AUTH).status_code == 422

    status = client.get("/api/index").json()
    assert status["documents"] == 2 and status["chunks"] == 9

    r = client.post("/api/retrieve", json={"embedding": [1, 0.05, 0], "embed_model": "test-embed"})
    assert r.status_code == 200, r.text
    contexts = r.json()["contexts"]
    # All leaves of a.md are within top-K, so they merge into their parent.
    assert contexts[0]["chunk_type"] == "parent"
    assert contexts[0]["file_path"] == "wiki/a.md"
    assert [c["source_num"] for c in contexts] == list(range(1, len(contexts) + 1))

    r = client.post("/api/retrieve", json={"embedding": [1, 0, 0], "embed_model": "other"})
    assert r.status_code == 409

    r = client.post("/api/expand", json={"query": "Wat staat er in de brp?"})
    assert r.json()["query"] == "Wat staat er in de BRP (Basisregistratie Personen)?"

    assert client.delete("/api/index/documents", params={"file_path": "wiki/b.md"}, headers=AUTH).status_code == 204
    assert client.get("/api/index").json()["documents"] == 1

    assert client.get("/api/config").json()["embed_model"] == "test-embed"


def test_conversations(client):
    r = client.post(
        "/api/conversations",
        json={"messages": [
            {"role": "user", "content": "Wat is BRP?", "effective_query": "Wat is BRP (Basisregistratie Personen)?"},
            {"role": "assistant", "content": "De bron.", "sources": [{"source_num": 1}], "model": "m", "duration_ms": 5},
        ]},
    )
    assert r.status_code == 201, r.text
    conversation = r.json()
    assert conversation["title"] == "Wat is BRP?"
    cid = conversation["id"]

    r = client.post(f"/api/conversations/{cid}/messages", json={"messages": [{"role": "user", "content": "En nu?"}]})
    assert r.status_code == 201

    full = client.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant", "user"]
    assert full["messages"][1]["sources"] == [{"source_num": 1}]

    assert client.patch(f"/api/conversations/{cid}", json={"title": "BRP"}).json()["title"] == "BRP"
    assert any(c["id"] == cid for c in client.get("/api/conversations").json()["conversations"])

    assert client.delete(f"/api/conversations/{cid}").status_code == 204
    assert client.get(f"/api/conversations/{cid}").status_code == 404


def test_sources_and_token_check(client):
    assert client.get("/api/index/auth").status_code == 401
    assert client.get("/api/index/auth", headers=AUTH).json() == {"ok": True}

    folder = client.post("/api/index/sources", json={"path": "/handboek/"}, headers=AUTH)
    assert folder.status_code == 201, folder.text
    assert folder.json()["path"] == "handboek" and folder.json()["documents"] == 1
    single = client.post("/api/index/sources", json={"path": "team/renovate.docx"}, headers=AUTH)
    assert single.status_code == 201 and single.json()["documents"] == 1

    assert client.post("/api/index/sources", json={"path": "handboek"}, headers=AUTH).status_code == 409
    assert client.post("/api/index/sources", json={"path": "bestaat-niet"}, headers=AUTH).status_code == 422
    escape = client.post("/api/index/sources", json={"path": "../../etc"}, headers=AUTH)
    assert escape.status_code == 422 and ".." in escape.json()["detail"]

    settings = client.get("/api/index/settings").json()
    assert [s["path"] for s in settings["sources"]] == ["handboek", "team/renovate.docx"]
    assert settings["documents_root_exists"] is True

    listing = client.get("/api/index/files", headers=AUTH).json()
    assert listing == {"files": ["handboek/brp.md", "team/renovate.docx"], "missing": []}

    browse = client.get("/api/index/browse").json()
    assert browse == {"path": "", "folders": ["handboek", "team"], "documents": ["geheim.md"]}
    assert client.get("/api/index/browse", params={"path": "../"}).status_code == 404

    for source in (folder.json(), single.json()):
        assert client.delete(f"/api/index/sources/{source['id']}", headers=AUTH).status_code == 204


def test_prepare_reads_splits_and_skips_unchanged(client, docs_root):
    client.put("/api/index/meta", json={**META, "reset": True}, headers=AUTH)
    body = {"file_path": "handboek/brp.md"}

    r = client.post("/api/index/prepare", json=body, headers=AUTH).json()
    assert r["status"] == "new"
    doc = r["document"]
    assert doc["source_url"] == "/api/files/handboek/brp.md"
    leaves = [n for n in doc["nodes"] if n["is_leaf"]]
    assert leaves and len(leaves) > len(doc["nodes"]) - len(leaves)
    assert all("brp.md" in n["embed_text"] and "/api/files" not in n["embed_text"] for n in leaves)

    doc["nodes"] = [{**n, "embedding": [1.0, 0.0, 0.0] if n["is_leaf"] else None} for n in doc["nodes"]]
    assert client.put("/api/index/documents", json=doc, headers=AUTH).status_code == 200

    again = client.post("/api/index/prepare", json=body, headers=AUTH).json()
    assert again["status"] == "unchanged"

    (docs_root / "handboek" / "brp.md").write_text("Nu staat er iets anders over de BRP. " * 50)
    assert client.post("/api/index/prepare", json=body, headers=AUTH).json()["status"] == "changed"

    docx = client.post("/api/index/prepare", json={"file_path": "team/renovate.docx"}, headers=AUTH).json()
    assert "Renovate-proces" in docx["document"]["content"]

    assert client.post("/api/index/prepare", json={"file_path": "../x.md"}, headers=AUTH).status_code == 422
    assert client.post("/api/index/prepare", json={"file_path": "handboek/notities.xyz"}, headers=AUTH).status_code == 404


def test_serves_original_documents(client):
    r = client.get("/api/files/team/renovate.docx")
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("inline")
    assert client.get("/api/files/geheim.md").text == "los bestand in de root"
    assert client.get("/api/files/handboek/notities.xyz").status_code == 404
    assert client.get("/api/files/..%2F..%2Fetc%2Fpasswd").status_code == 404
