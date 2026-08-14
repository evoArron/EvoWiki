from fastapi.testclient import TestClient

from app.main import create_app


def test_authorized_member_can_lazily_read_a_project_document_tree(tmp_path):
    app = create_app(
        database_path=tmp_path / "evowiki.db",
        database_root=tmp_path,
        wiki_root=tmp_path / "enterprise-wiki-repo",
        jwt_secret="test-secret",
        initial_admin_username="admin",
        initial_admin_password="correct-horse-battery-staple",
    )
    client = TestClient(app)
    admin_token = client.post(
        "/api/auth/login", json={"username": "admin", "password": "correct-horse-battery-staple"}
    ).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    client.post("/api/admin/users", headers=admin_headers, json={"username": "reader", "password": "reader-password"})
    client.post("/api/admin/projects", headers=admin_headers, json={"project_id": "alpha"})
    client.post(
        "/api/admin/projects/alpha/permissions",
        headers=admin_headers,
        json={"username": "reader", "role": "viewer"},
    )
    docs = tmp_path / "enterprise-wiki-repo" / "alpha" / "docs"
    (docs / "design").mkdir()
    (docs / "intro.md").write_text("# Intro", encoding="utf-8")

    reader_token = client.post("/api/auth/login", json={"username": "reader", "password": "reader-password"}).json()["access_token"]
    response = client.get("/api/projects/alpha/tree", headers={"Authorization": f"Bearer {reader_token}"})

    assert response.status_code == 200
    assert response.json() == [
        {"title": "design", "key": "docs/design", "is_leaf": False},
        {"title": "intro.md", "key": "docs/intro.md", "is_leaf": True},
    ]


def test_document_tree_rejects_unassigned_projects_and_paths_outside_docs(tmp_path):
    app = create_app(
        database_path=tmp_path / "evowiki.db",
        database_root=tmp_path,
        wiki_root=tmp_path / "enterprise-wiki-repo",
        jwt_secret="test-secret",
        initial_admin_username="admin",
        initial_admin_password="correct-horse-battery-staple",
    )
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-battery-staple"}).json()["access_token"]

    client.post("/api/admin/projects", headers={"Authorization": f"Bearer {token}"}, json={"project_id": "alpha"})
    unknown_project = client.get("/api/projects/missing/tree", headers={"Authorization": f"Bearer {token}"})
    escaped_path = client.get("/api/projects/alpha/tree", params={"path": "../"}, headers={"Authorization": f"Bearer {token}"})

    assert unknown_project.status_code == 403
    assert escaped_path.status_code == 422
