import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.publishing import ChromaIndexer


def create_test_app(tmp_path, git_runner=None, indexer=None):
    indexed = []
    app = create_app(
        database_path=tmp_path / "evowiki.db",
        database_root=tmp_path,
        wiki_root=tmp_path / "enterprise-wiki-repo",
        jwt_secret="test-secret",
        initial_admin_username="admin",
        initial_admin_password="correct-horse-battery-staple",
        git_runner=git_runner or (lambda arguments, _: "test-commit\n" if arguments == ["rev-parse", "HEAD"] else ""),
        indexer=indexer or (lambda *record: indexed.append(record)),
    )
    return TestClient(app), indexed


def login(client, username, password):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': username, 'password': password}).json()['access_token']}"}


def create_editor(client, admin_headers):
    member = client.post("/api/admin/members", headers=admin_headers, json={"username": "editor", "display_name": "Editor"}).json()
    temporary_headers = login(client, "editor", member["temporary_password"])
    client.post("/api/auth/change-password", headers=temporary_headers, json={"current_password": member["temporary_password"], "new_password": "editor-password"})
    client.post("/api/admin/projects", headers=admin_headers, json={"project_id": "alpha", "owner_username": "editor"})
    return login(client, "editor", "editor-password")


def test_editor_can_review_reject_and_publish_a_draft_without_indexing_before_push(tmp_path):
    client, indexed = create_test_app(tmp_path)
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    editor_headers = create_editor(client, admin_headers)

    created = client.post("/api/projects/alpha/drafts", headers=editor_headers, json={"path": "design.md", "content": "# First"})
    draft_id = created.json()["id"]
    assert created.status_code == 201
    assert client.get(f"/api/projects/alpha/drafts/{draft_id}", headers=editor_headers).json()["content"] == "# First"
    assert client.put(f"/api/projects/alpha/drafts/{draft_id}", headers=editor_headers, json={"content": "# Revised"}).status_code == 200
    assert client.delete(f"/api/projects/alpha/drafts/{draft_id}", headers=editor_headers).status_code == 204
    assert client.post(f"/api/projects/alpha/drafts/{draft_id}/publish", headers=editor_headers, json={"target_path": "design.md"}).status_code == 409
    assert indexed == []

    published = client.post("/api/projects/alpha/drafts", headers=editor_headers, json={"path": "ready.md", "content": "# Ready"})
    publication_id = published.json()["id"]
    result = client.post(f"/api/projects/alpha/drafts/{publication_id}/publish", headers=editor_headers, json={"target_path": "architecture.md"})

    assert result.status_code == 200
    assert result.json()["status"] == "indexed"
    assert result.json()["git_commit"] == "test-commit"
    assert indexed == [("alpha", "alpha/docs/architecture.md", "# Ready", "test-commit")]
    assert (tmp_path / "enterprise-wiki-repo" / "alpha" / "docs" / "architecture.md").read_text() == "# Ready"
    assert client.get("/api/projects/alpha/documents", headers=editor_headers, params={"path": "docs/architecture.md"}).json() == {"path": "docs/architecture.md", "content": "# Ready", "git_commit": "test-commit"}


def test_mcp_upload_stays_pending_until_human_publish(tmp_path):
    client, _ = create_test_app(tmp_path)
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    editor_headers = create_editor(client, admin_headers)
    token = editor_headers["Authorization"].removeprefix("Bearer ")

    _, uploaded = asyncio.run(client.app.state.mcp.call_tool("upload_draft", {"access_token": token, "project_id": "alpha", "path": "mcp.md", "content": "# MCP"}))

    assert uploaded["status"] == "pending"
    assert client.get("/api/projects/alpha/drafts", headers=editor_headers).json()[0]["draft_path"] == "alpha/.drafts/mcp.md"


def test_chroma_indexer_keeps_code_fences_whole_and_returns_source_metadata(tmp_path):
    indexer = ChromaIndexer(tmp_path / "chroma")
    indexer("alpha", "alpha/docs/design.md", "# Design\n```python\n# not a heading\n```\n# API\ncontent", "commit-1")

    results = indexer.search(["alpha"], "API")

    assert results
    assert all(result["path"] == "alpha/docs/design.md" and result["git_commit"] == "commit-1" for result in results)
    assert any("# not a heading" in result["chunk"] for result in results)


def test_failed_push_is_not_indexed_and_retry_does_not_create_another_commit(tmp_path):
    attempts = {"push": 0, "commit": 0}
    indexed = []
    def git_runner(arguments, _):
        if arguments[0] == "commit": attempts["commit"] += 1
        if arguments == ["push"]:
            attempts["push"] += 1
            if attempts["push"] == 1: raise RuntimeError("remote unavailable")
        return "test-commit\n" if arguments == ["rev-parse", "HEAD"] else ""

    client, _ = create_test_app(tmp_path, git_runner=git_runner, indexer=lambda *record: indexed.append(record))
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    editor_headers = create_editor(client, admin_headers)
    draft = client.post("/api/projects/alpha/drafts", headers=editor_headers, json={"path": "retry.md", "content": "# Retry"}).json()
    failed = client.post(f"/api/projects/alpha/drafts/{draft['id']}/publish", headers=editor_headers, json={"target_path": "retry.md"})

    assert failed.json()["status"] == "failed"
    assert indexed == []

    retried = client.post(f"/api/projects/alpha/drafts/{draft['id']}/retry", headers=editor_headers)

    assert retried.json()["status"] == "indexed"
    assert attempts == {"push": 2, "commit": 1}
    assert indexed == [("alpha", "alpha/docs/retry.md", "# Retry", "test-commit")]


def test_draft_upload_rejects_viewers_non_markdown_and_escaped_paths(tmp_path):
    client, _ = create_test_app(tmp_path)
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    viewer = client.post("/api/admin/members", headers=admin_headers, json={"username": "viewer", "display_name": "Viewer"}).json()
    viewer_headers = login(client, "viewer", viewer["temporary_password"])
    client.post("/api/auth/change-password", headers=viewer_headers, json={"current_password": viewer["temporary_password"], "new_password": "viewer-password"})
    client.post("/api/admin/projects", headers=admin_headers, json={"project_id": "alpha"})
    client.post("/api/admin/projects/alpha/permissions", headers=admin_headers, json={"username": "viewer", "role": "viewer"})
    member = client.post("/api/admin/members", headers=admin_headers, json={"username": "writer", "display_name": "Writer"}).json()
    temporary_headers = login(client, "writer", member["temporary_password"])
    client.post("/api/auth/change-password", headers=temporary_headers, json={"current_password": member["temporary_password"], "new_password": "writer-password"})
    client.post("/api/admin/projects/alpha/permissions", headers=admin_headers, json={"username": "writer", "role": "editor"})

    assert client.post("/api/projects/alpha/drafts", headers=login(client, "viewer", "viewer-password"), json={"path": "note.md", "content": "x"}).status_code == 403
    writer_headers = login(client, "writer", "writer-password")
    assert client.post("/api/projects/alpha/drafts", headers=writer_headers, json={"path": "note.txt", "content": "x"}).status_code == 422
    assert client.post("/api/projects/alpha/drafts", headers=writer_headers, json={"path": "../escape.md", "content": "x"}).status_code == 422
