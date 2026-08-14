import os

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_app(tmp_path):
    return create_app(
        database_path=tmp_path / "evowiki.db",
        database_root=tmp_path,
        wiki_root=tmp_path / "enterprise-wiki-repo",
        jwt_secret="test-secret",
        initial_admin_username="admin",
        initial_admin_password="correct-horse-battery-staple",
    )


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_authorized_reader(client: TestClient) -> dict[str, str]:
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": "reader", "display_name": "Reader", "password": "reader-password"},
    )
    client.post("/api/admin/projects", headers=admin_headers, json={"project_id": "alpha"})
    client.post(
        "/api/admin/projects/alpha/permissions",
        headers=admin_headers,
        json={"username": "reader", "role": "viewer"},
    )
    temporary_headers = login(client, "reader", "reader-password")
    response = client.post(
        "/api/auth/change-password",
        headers=temporary_headers,
        json={"current_password": "reader-password", "new_password": "reader-password-active"},
    )
    assert response.status_code == 204
    return login(client, "reader", "reader-password-active")


def test_authorized_member_can_lazily_read_a_project_document_tree(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    reader_headers = create_authorized_reader(client)
    docs = tmp_path / "enterprise-wiki-repo" / "alpha" / "docs"
    (docs / "design").mkdir()
    (docs / "intro.md").write_text("# Intro", encoding="utf-8")

    response = client.get("/api/projects/alpha/tree", headers=reader_headers)

    assert response.status_code == 200
    assert response.json() == [
        {"title": "design", "key": "docs/design", "is_leaf": False},
        {"title": "intro.md", "key": "docs/intro.md", "is_leaf": True},
    ]


def test_document_tree_rejects_unassigned_projects_and_paths_outside_docs(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    headers = login(client, "admin", "correct-horse-battery-staple")
    client.post("/api/admin/projects", headers=headers, json={"project_id": "alpha"})

    unknown_project = client.get("/api/projects/missing/tree", headers=headers)
    escaped_path = client.get("/api/projects/alpha/tree", params={"path": "../"}, headers=headers)
    escaped_document = client.get("/api/projects/alpha/documents", params={"path": "docs/../secret.md"}, headers=headers)
    non_markdown_document = client.get("/api/projects/alpha/documents", params={"path": "docs/note.txt"}, headers=headers)

    assert unknown_project.status_code == 404
    assert escaped_path.status_code == 422
    assert escaped_document.status_code == 422
    assert non_markdown_document.status_code == 422


def test_document_tree_rejects_docs_symlink_outside_project(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    headers = login(client, "admin", "correct-horse-battery-staple")
    client.post("/api/admin/projects", headers=headers, json={"project_id": "alpha"})
    docs = tmp_path / "enterprise-wiki-repo" / "alpha" / "docs"
    docs.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, docs, target_is_directory=True)

    response = client.get("/api/projects/alpha/tree", headers=headers)

    assert response.status_code == 422


def test_authorized_member_can_read_a_published_markdown_document(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    reader_headers = create_authorized_reader(client)
    (tmp_path / "enterprise-wiki-repo" / "alpha" / "docs" / "intro.md").write_text(
        "# Intro\n\nPublished content.", encoding="utf-8"
    )

    response = client.get("/api/projects/alpha/documents", params={"path": "docs/intro.md"}, headers=reader_headers)

    assert response.status_code == 200
    assert response.json() == {"path": "docs/intro.md", "content": "# Intro\n\nPublished content."}
