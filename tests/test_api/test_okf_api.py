"""OKF knowledge API + conversations: human-only writes, conflicts, review flow, import/export.

Bundles live in a temp dir and the Qdrant/Neo4j projections are replaced by recorders, so
these tests never write to the live databases.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api import services
from apps.api.main import app
from apps.api.storage import ConversationStore
from core.config import settings

AGENT = "eih_agent/qwen2.5-coder-7b"


class Recorder:
    def __init__(self):
        self.calls = []

    def sync_concepts(self, bundle, name, ids):
        self.calls.append((name, list(ids)))
        return {}

    def sync_bundle(self, bundle, name):
        self.calls.append((name, "all"))
        return {"concepts": len(bundle.concepts)}

    def search(self, q, bundle=None, limit=8):
        return []


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    root = tmp_path / "bundles"
    (root / "kb" / "apis").mkdir(parents=True)
    (root / "kb" / "apis" / "auth.md").write_text(
        "---\ntype: API Endpoint\ntitle: Auth\ndescription: Login.\n---\n\nSee [db](/infra/db.md).\n", encoding="utf-8")
    monkeypatch.setattr(settings.okf, "root", root)
    monkeypatch.setattr(settings.okf, "state_dir", tmp_path / "state")
    monkeypatch.setattr(settings.okf, "default_bundle", "kb")
    rec = Recorder()
    monkeypatch.setattr(services, "_workspaces", {})
    monkeypatch.setattr(services, "vector_index", lambda: rec)
    monkeypatch.setattr(services, "graph_projection", lambda: rec)
    monkeypatch.setattr(services, "_conversations", ConversationStore(tmp_path / "state" / "app.sqlite3"))
    c = TestClient(app)
    c.recorder = rec
    return c


def test_bundle_listing_tree_and_concept_detail(client):
    b = client.get("/okf/bundles").json()
    assert [(x["name"], x["concepts"], x["conformant"], x["broken_links"]) for x in b] == [("kb", 1, True, 1)]
    tree = client.get("/okf/bundles/kb/tree").json()
    assert tree["count"] == 1 and tree["dirs"][0]["name"] == "apis"
    d = client.get("/okf/bundles/kb/concept/apis/auth").json()
    assert d["type"] == "API Endpoint" and d["trust_tier"] == "unverified"
    assert d["links"][0]["broken"] is True
    assert client.get("/okf/bundles/kb/concept/nope").status_code == 404
    assert client.get("/okf/bundles/missing/tree").status_code == 404


def test_human_edit_create_conflict_and_actor_validation(client):
    body = {"frontmatter": {"type": "Component", "title": "DB"}, "body": "Postgres 16.\n", "actor": "human:ava"}
    r = client.put("/okf/bundles/kb/concept/infra/db", json=body)
    assert r.status_code == 200 and client.recorder.calls == [("kb", ["infra/db"]), ("kb", ["infra/db"])]
    detail = client.get("/okf/bundles/kb/concept/infra/db").json()
    assert detail["trust_tier"] == "human-reviewed" and detail["generated_by"] == "human:ava"
    assert client.get("/okf/bundles/kb/concept/apis/auth").json()["links"][0]["broken"] is False
    stale = dict(body, base_hash="0" * 64)
    assert client.put("/okf/bundles/kb/concept/infra/db", json=stale).status_code == 409
    assert client.put("/okf/bundles/kb/concept/infra/x", json=dict(body, actor=AGENT)).status_code == 422
    assert client.put("/okf/bundles/kb/concept/../escape", json=body).status_code in (400, 404)


def test_agent_proposal_review_flow(client):
    ws = services.workspace("kb")
    p = ws.propose(kind="create", concept_id="infra/cache", frontmatter={"type": "Component", "title": "Cache"},
                   body="Redis.\n", rationale="Asked about caching.", actor=AGENT)
    listed = client.get("/okf/bundles/kb/proposals", params={"status": "pending"}).json()
    assert [x["id"] for x in listed] == [p.id]
    assert client.get(f"/okf/bundles/kb/proposals/{p.id}").json()["current"] is None
    bad = client.post(f"/okf/bundles/kb/proposals/{p.id}/approve", json={"reviewer": AGENT})
    assert bad.status_code == 422
    ok = client.post(f"/okf/bundles/kb/proposals/{p.id}/approve", json={"reviewer": "human:ava", "note": "fine"})
    assert ok.json()["status"] == "approved"
    c = client.get("/okf/bundles/kb/concept/infra/cache").json()
    assert c["generated_by"] == AGENT and c["trust_tier"] == "human-reviewed"
    assert [h["action"] for h in c["history"]] == ["approve", "propose"]
    assert "approved by `human:ava`" in client.get("/okf/bundles/kb/log").json()["log"]


def test_export_is_plain_markdown_and_import_validates(client, tmp_path):
    z = client.get("/okf/bundles/kb/export")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "kb/apis/auth.md" in names and not any(".eih_state" in n for n in names)
    r = client.post("/okf/import", params={"name": "copy", "sync": "true"},
                    files={"file": ("kb.zip", z.content, "application/zip")})
    assert r.status_code == 200 and r.json()["conformance"]["conformant"]
    assert ("copy", "all") in client.recorder.calls
    assert client.post("/okf/import", params={"name": "copy"},
                       files={"file": ("kb.zip", z.content, "application/zip")}).status_code == 409
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../evil.md", "---\ntype: X\n---\n")
    assert client.post("/okf/import", params={"name": "evil"},
                       files={"file": ("e.zip", evil.getvalue(), "application/zip")}).status_code == 400


def test_conversations_crud(client):
    store = services.conversations()
    conv = store.create("First question", "kb")
    store.add_message(conv["id"], "user", "hello")
    store.add_message(conv["id"], "assistant", "hi", meta={"citations": ["okf:apis/auth"]})
    assert client.get("/conversations").json()[0]["message_count"] == 2
    got = client.get(f"/conversations/{conv['id']}").json()
    assert [m["role"] for m in got["messages"]] == ["user", "assistant"]
    assert got["messages"][1]["meta"]["citations"] == ["okf:apis/auth"]
    assert client.get("/conversations", params={"q": "hello"}).json()[0]["id"] == conv["id"]
    assert client.patch(f"/conversations/{conv['id']}", json={"title": "Renamed"}).status_code == 200
    assert client.delete(f"/conversations/{conv['id']}").status_code == 200
    assert client.get(f"/conversations/{conv['id']}").status_code == 404


def test_chat_refuses_without_llm(client, monkeypatch):
    class Down:
        def is_available(self):
            return False
    monkeypatch.setattr(services, "llm", lambda: Down())
    r = client.post("/chat", json={"question": "How does auth work?"})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]
