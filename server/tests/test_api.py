"""End-to-end over the HTTP API against a real Postgres with pgvector.

Needs the DB_* variables (CI sets them; locally: a database started from
database/ with init.sql applied). Skipped without DB_HOST.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DB_HOST"), reason="needs a database (DB_HOST)")

TOKEN = "test-token"


@pytest.fixture(scope="module")
def client():
    os.environ["INDEX_TOKEN"] = TOKEN
    from app import config

    config.INDEX_TOKEN = TOKEN
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
        "source_url": f"https://gitlab.example/{path}",
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

    wiki = client.post("/api/index/sources", json={"url": "https://gitlab.example/team/x/-/wikis/"}, headers=AUTH)
    assert wiki.status_code == 201 and wiki.json()["kind"] == "wiki"
    assert wiki.json()["url"] == "https://gitlab.example/team/x/-/wikis"
    repo = client.post("/api/index/sources", json={"url": "https://gitlab.example/team/y"}, headers=AUTH)
    assert repo.json()["kind"] == "repo"
    dup = client.post("/api/index/sources", json={"url": "https://gitlab.example/team/y"}, headers=AUTH)
    assert dup.status_code == 409
    assert client.post("/api/index/sources", json={"url": "not a url"}, headers=AUTH).status_code == 422

    settings = client.get("/api/index/settings").json()
    assert [s["kind"] for s in settings["sources"]][-2:] == ["wiki", "repo"]
    assert settings["chunk_config"] == {"parent_chunk_size": 1500, "child_chunk_size": 375, "parent_chunk_overlap": 300}

    for source in (wiki.json(), repo.json()):
        assert client.delete(f"/api/index/sources/{source['id']}", headers=AUTH).status_code == 204


def test_prepare_splits_new_text_and_skips_unchanged(client):
    client.put("/api/index/meta", json={**META, "reset": True}, headers=AUTH)
    text = " ".join(f"Zin {i} over de Basisregistratie Personen (BRP)." for i in range(400))
    body = {"file_path": "https://g/x/-/wikis/brp", "file_name": "brp.md", "source_url": "https://g/x/-/wikis/brp", "text": text}

    r = client.post("/api/index/prepare", json=body, headers=AUTH).json()
    assert r["status"] == "new"
    nodes = r["document"]["nodes"]
    leaves = [n for n in nodes if n["is_leaf"]]
    assert leaves and len(leaves) > len(nodes) - len(leaves)
    assert all(n["embed_text"] and "brp.md" in n["embed_text"] and r["content_hash"] not in n["embed_text"] for n in leaves)

    # Store it with embeddings, as the browser does after asking Ollama.
    doc = r["document"]
    doc["nodes"] = [{**n, "embedding": [1.0, 0.0, 0.0] if n["is_leaf"] else None} for n in nodes]
    assert client.put("/api/index/documents", json=doc, headers=AUTH).status_code == 200

    again = client.post("/api/index/prepare", json=body, headers=AUTH).json()
    assert again == {"file_path": body["file_path"], "status": "unchanged", "content_hash": r["content_hash"]}
    changed = client.post("/api/index/prepare", json={**body, "text": text + " Nieuw."}, headers=AUTH).json()
    assert changed["status"] == "changed"


def test_prepare_extracts_docx(client):
    import base64
    import io

    import docx

    document = docx.Document()
    document.add_paragraph("Het Renovate-proces opent pull requests.")
    buffer = io.BytesIO()
    document.save(buffer)
    body = {"file_path": "repo/docs/renovate.docx", "file_name": "renovate.docx",
            "data_base64": base64.b64encode(buffer.getvalue()).decode()}
    r = client.post("/api/index/prepare", json=body, headers=AUTH).json()
    assert r["status"] == "new"
    assert "Renovate-proces" in r["document"]["content"]

    bad = client.post("/api/index/prepare", json={**body, "file_name": "x.exe"}, headers=AUTH)
    assert bad.status_code == 422
