"""End-to-end over the HTTP API against a real Postgres with pgvector.

Needs the DB_* variables (CI sets them; locally: a database started from
database/ with init.sql applied). Skipped without DB_HOST.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DB_HOST"), reason="needs a database (DB_HOST)")

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
META = {"embed_model": "test-embed", "embed_dimensions": 3}


@pytest.fixture(scope="module")
def docs_root(tmp_path_factory):
    """A documents folder like the one mounted on the NAS."""
    import docx

    root = tmp_path_factory.mktemp("documents")
    (root / "bv").mkdir()
    (root / "bv" / "brp.md").write_text(
        " ".join(f"Zin {i} over de Basisregistratie Personen (BRP)." for i in range(400))
    )
    (root / "bv" / "notities.xyz").write_text("niet ondersteund")
    (root / "bv" / ".verborgen.md").write_text("verborgen")
    (root / "bv" / "archief").mkdir()
    (root / "bv" / "archief" / "oud.md").write_text("Oude informatie over facturen. " * 20)
    (root / "bv" / "concept-plan.md").write_text("Een concept. " * 20)
    (root / "team").mkdir()
    d = docx.Document()
    d.add_paragraph("Het Renovate-proces opent pull requests.")
    d.save(root / "team" / "renovate.docx")
    (root / "los.md").write_text("los bestand in de root")
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
        # Start from a clean store; the demo seed may have added an index.
        for i in c.get("/api/indexes").json()["indexes"]:
            c.delete(f"/api/indexes/{i['id']}", headers=AUTH)
        c.put("/api/index/meta", json={**META, "reset": True}, headers=AUTH)
        yield c


def new_index(client, name: str, *sources: str, ignore: str = "") -> dict:
    index = client.post("/api/indexes", json={"name": name}, headers=AUTH)
    assert index.status_code == 201, index.text
    index_id = index.json()["id"]
    for path in sources:
        assert client.post(f"/api/indexes/{index_id}/sources", json={"path": path}, headers=AUTH).status_code == 201
    if ignore:
        client.patch(f"/api/indexes/{index_id}", json={"ignore_patterns": ignore}, headers=AUTH)
    return client.get(f"/api/indexes/{index_id}").json()


# Fake embeddings: every document points its own way, so a search can find each.
DIRECTIONS = {"bv/brp.md": [1.0, 0.0, 0.0], "team/renovate.docx": [0.0, 0.0, 1.0]}


def index_run(client, index_id: int) -> dict:
    """What the browser does: list, prepare, embed (fake), store, prune."""
    listing = client.get(f"/api/indexes/{index_id}/files", headers=AUTH).json()
    statuses = {}
    for path in listing["files"]:
        r = client.post("/api/index/prepare", json={"file_path": path, "index_id": index_id}, headers=AUTH)
        assert r.status_code == 200, r.text
        prepared = r.json()
        statuses[path] = prepared["status"]
        if prepared["status"] in ("new", "changed"):
            doc = prepared["document"]
            doc["index_id"] = index_id
            vector = DIRECTIONS.get(path, [0.0, 1.0, 0.0])
            doc["nodes"] = [{**n, "embedding": vector if n["is_leaf"] else None} for n in doc["nodes"]]
            assert client.put("/api/index/documents", json=doc, headers=AUTH).status_code == 200
    pruned = client.post(f"/api/indexes/{index_id}/prune", json={"keep": listing["files"]}, headers=AUTH).json()
    return {"files": listing["files"], "statuses": statuses, **pruned}


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and "version" in body


def test_changes_need_the_token(client):
    assert client.get("/api/index/auth").status_code == 401
    assert client.get("/api/index/auth", headers=AUTH).json() == {"ok": True}
    assert client.post("/api/indexes", json={"name": "X"}).status_code == 401
    assert client.put("/api/index/meta", json=META).status_code == 401


def test_indexes_sources_and_ignore_patterns(client):
    bv = new_index(client, "Mijn BV", "/bv/")
    assert bv["sources"][0]["path"] == "bv"
    # brp.md, archief/oud.md and concept-plan.md; hidden and unsupported files never count.
    assert bv["sources"][0]["documents"] == 3

    assert client.post("/api/indexes", json={"name": "Mijn BV"}, headers=AUTH).status_code == 409
    assert client.post(f"/api/indexes/{bv['id']}/sources", json={"path": "bv"}, headers=AUTH).status_code == 409
    assert client.post(f"/api/indexes/{bv['id']}/sources", json={"path": "bestaat-niet"}, headers=AUTH).status_code == 422
    escape = client.post(f"/api/indexes/{bv['id']}/sources", json={"path": "../../etc"}, headers=AUTH)
    assert escape.status_code == 422 and ".." in escape.json()["detail"]

    # gitignore syntax against paths relative to the documents folder.
    r = client.patch(f"/api/indexes/{bv['id']}", json={"ignore_patterns": "archief/\r\nconcept*\n# notitie\n"}, headers=AUTH)
    assert r.json()["ignore_patterns"] == "archief/\nconcept*\n# notitie\n"
    assert r.json()["sources"][0]["documents"] == 1
    assert client.get(f"/api/indexes/{bv['id']}/files", headers=AUTH).json() == {"files": ["bv/brp.md"], "missing": []}

    renamed = client.patch(f"/api/indexes/{bv['id']}", json={"name": "Mijn BV bv"}, headers=AUTH).json()
    assert renamed["name"] == "Mijn BV bv"

    assert client.get("/api/index/browse").status_code == 401
    browse = client.get("/api/index/browse", headers=AUTH).json()
    assert browse == {"path": "", "folders": ["bv", "team"], "documents": ["los.md"]}

    client.delete(f"/api/indexes/{bv['id']}", headers=AUTH)


def test_shared_documents_and_search_per_index(client):
    a = new_index(client, "A", "bv/brp.md", "team")
    b = new_index(client, "B", "bv/brp.md")

    run_a = index_run(client, a["id"])
    assert run_a["statuses"] == {"bv/brp.md": "new", "team/renovate.docx": "new"}
    # B shares brp.md: already split and embedded, it just joins B.
    run_b = index_run(client, b["id"])
    assert run_b["statuses"] == {"bv/brp.md": "unchanged"}

    status = client.get("/api/index").json()
    assert status["documents"] == 2 and status["indexes"] == 2
    assert client.get(f"/api/indexes/{a['id']}").json()["documents"] == 2
    assert client.get(f"/api/indexes/{b['id']}").json()["documents"] == 1

    def search(index_id, vector=(1, 0, 0)):
        r = client.post("/api/retrieve", json={"embedding": list(vector), "embed_model": "test-embed", "index_id": index_id})
        assert r.status_code == 200, r.text
        return [c["file_path"] for c in r.json()["contexts"]]

    # A question about Renovate finds it first in A; B does not contain it at all.
    assert search(a["id"], (0, 0, 1))[0] == "team/renovate.docx"
    assert "team/renovate.docx" not in search(b["id"], (0, 0, 1))
    assert set(search(b["id"])) == {"bv/brp.md"}

    # Abbreviations come only from the conversation's index.
    q = "Wat staat er in de brp?"
    assert client.post("/api/expand", json={"query": q, "index_id": b["id"]}).json()["query"] == (
        "Wat staat er in de BRP (Basisregistratie Personen)?"
    )
    empty = new_index(client, "Leeg", "los.md")
    assert client.post("/api/expand", json={"query": q, "index_id": empty["id"]}).json()["query"] == q

    # Replacing a shared document keeps it in the other index.
    assert client.post("/api/index/prepare", json={"file_path": "bv/brp.md"}, headers=AUTH).json()["status"] == "unchanged"
    doc = client.post("/api/index/prepare", json={"file_path": "team/renovate.docx"}, headers=AUTH)
    assert doc.json()["status"] == "unchanged"

    # Removing a source drops its documents from that index at the next run;
    # brp.md stays because B still has it, renovate.docx goes entirely.
    source_id = next(s["id"] for s in client.get(f"/api/indexes/{a['id']}").json()["sources"] if s["path"] == "team")
    client.delete(f"/api/indexes/{a['id']}/sources/{source_id}", headers=AUTH)
    pruned = index_run(client, a["id"])
    assert pruned["removed"] == 1 and pruned["deleted_documents"] == 1
    assert set(search(b["id"])) == {"bv/brp.md"}

    # Deleting index B leaves brp.md for A.
    client.delete(f"/api/indexes/{b['id']}", headers=AUTH)
    assert set(search(a["id"], (0, 0, 1))) == {"bv/brp.md"}

    assert client.get("/api/config").json()["embed_model"] == "test-embed"
    for i in (a, empty):
        client.delete(f"/api/indexes/{i['id']}", headers=AUTH)
    assert client.get("/api/index").json()["documents"] == 0


def test_store_validates_embeddings(client):
    idx = new_index(client, "Validatie", "bv/brp.md")
    prepared = client.post("/api/index/prepare", json={"file_path": "bv/brp.md", "index_id": idx["id"]}, headers=AUTH).json()
    doc = {**prepared["document"], "index_id": idx["id"]}
    doc["nodes"] = [{**n, "embedding": [1.0, 0.0] if n["is_leaf"] else None} for n in doc["nodes"]]
    assert client.put("/api/index/documents", json=doc, headers=AUTH).status_code == 422
    assert client.post("/api/index/prepare", json={"file_path": "../x.md"}, headers=AUTH).status_code == 422
    assert client.post("/api/index/prepare", json={"file_path": "bv/notities.xyz"}, headers=AUTH).status_code == 404
    # A different model without reset is refused.
    assert client.put("/api/index/meta", json={**META, "embed_model": "other"}, headers=AUTH).status_code == 409
    client.delete(f"/api/indexes/{idx['id']}", headers=AUTH)


def test_conversations_keep_their_index(client):
    idx = new_index(client, "Gesprekken", "los.md")
    assert client.post("/api/conversations", json={"messages": []}).status_code == 422
    r = client.post(
        "/api/conversations",
        json={"index_id": idx["id"], "messages": [
            {"role": "user", "content": "Wat is BRP?", "effective_query": "Wat is BRP (Basisregistratie Personen)?"},
            {"role": "assistant", "content": "De bron.", "sources": [{"source_num": 1}], "model": "m", "duration_ms": 5},
        ]},
    )
    assert r.status_code == 201, r.text
    conversation = r.json()
    assert conversation["title"] == "Wat is BRP?"
    assert conversation["index_id"] == idx["id"] and conversation["index_name"] == "Gesprekken"
    cid = conversation["id"]

    assert client.post(f"/api/conversations/{cid}/messages", json={"messages": [{"role": "user", "content": "En nu?"}]}).status_code == 201
    full = client.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant", "user"]
    assert client.patch(f"/api/conversations/{cid}", json={"title": "BRP"}).json()["index_name"] == "Gesprekken"

    # Deleting the index keeps the conversation readable, without an index.
    client.delete(f"/api/indexes/{idx['id']}", headers=AUTH)
    listed = next(c for c in client.get("/api/conversations").json()["conversations"] if c["id"] == cid)
    assert listed["index_id"] is None and listed["index_name"] is None

    assert client.delete(f"/api/conversations/{cid}").status_code == 204
    assert client.get(f"/api/conversations/{cid}").status_code == 404


def test_system_prompt_setting(client):
    default = client.put("/api/settings", json={"system_prompt": None}).json()
    assert default["system_prompt_is_default"] is True
    assert default["system_prompt"] == default["default_system_prompt"]

    r = client.put("/api/settings", json={"system_prompt": "  Antwoord in het Nederlands. Vandaag is {today}.  "}).json()
    assert r["system_prompt"] == "Antwoord in het Nederlands. Vandaag is {today}."
    assert r["system_prompt_is_default"] is False
    assert client.get("/api/config").json()["system_prompt"] == r["system_prompt"]

    back = client.put("/api/settings", json={"system_prompt": ""}).json()
    assert back["system_prompt_is_default"] is True
    assert client.get("/api/config").json()["system_prompt"] == default["default_system_prompt"]


def test_absolute_paths_on_the_nas(client, monkeypatch):
    """On the NAS the documents folder is /, and sources are typed as absolute paths."""
    from app import config

    monkeypatch.setattr(config, "DOCUMENTS_DIR", "/volume1/docs")
    index = new_index(client, "Absoluut", "/volume1/docs/bv/")
    assert [s["path"] for s in index["sources"]] == ["bv"]
    outside = client.post(f"/api/indexes/{index['id']}/sources", json={"path": "/home/elders"}, headers=AUTH)
    assert outside.status_code == 422 and "buiten de documentenmap" in outside.json()["detail"]
    assert client.get("/api/index/browse", params={"path": "/volume1/docs/bv"}, headers=AUTH).json()["path"] == "bv"

    # The whole NAS: never as one source, and its system folders are skipped.
    monkeypatch.setattr(config, "DOCUMENTS_DIR", "/")
    whole = client.post(f"/api/indexes/{index['id']}/sources", json={"path": "/"}, headers=AUTH)
    assert whole.status_code == 422
    assert client.post(f"/api/indexes/{index['id']}/sources", json={"path": "/team"}, headers=AUTH).status_code == 201
    client.delete(f"/api/indexes/{index['id']}", headers=AUTH)


def test_skips_system_folders_at_the_root(tmp_path, monkeypatch):
    from app import config, files

    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "x.txt").write_text("kernel")
    (tmp_path / "home" / "proc").mkdir(parents=True)
    (tmp_path / "home" / "proc" / "notes.md").write_text("gewone map")
    (tmp_path / "@docker").mkdir()
    (tmp_path / "@docker" / "y.md").write_text("synology")
    monkeypatch.setattr(config, "DOCUMENTS_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "DOCUMENTS_DIR", "/")
    assert files.list_documents("home") == ["home/proc/notes.md"]
    assert files.browse("/")["folders"] == ["home"]
    with pytest.raises(files.PathError):
        files.list_documents("")


def test_serves_only_indexed_documents(client):
    assert client.get("/api/files/los.md").status_code == 404
    index = new_index(client, "Bestanden", "team", "los.md")
    index_run(client, index["id"])
    r = client.get("/api/files/team/renovate.docx")
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("inline")
    assert client.get("/api/files/los.md").text == "los bestand in de root"
    assert client.get("/api/files/bv/notities.xyz").status_code == 404
    assert client.get("/api/files/..%2F..%2Fetc%2Fpasswd").status_code == 404
    client.delete(f"/api/indexes/{index['id']}", headers=AUTH)
    assert client.get("/api/files/los.md").status_code == 404
