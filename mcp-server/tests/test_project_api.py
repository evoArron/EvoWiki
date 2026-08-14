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
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_can_grant_project_access_to_a_member(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_headers = login(client, "admin", "correct-horse-battery-staple")

    member = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": "reviewer", "password": "reviewer-password"},
    )
    project = client.post(
        "/api/admin/projects",
        headers=admin_headers,
        json={"project_id": "alpha"},
    )
    permission = client.post(
        "/api/admin/projects/alpha/permissions",
        headers=admin_headers,
        json={"username": "reviewer", "role": "viewer"},
    )

    assert member.status_code == 201
    assert project.status_code == 201
    assert permission.status_code == 200
    assert (tmp_path / "enterprise-wiki-repo" / "alpha" / "docs").is_dir()

    member_headers = login(client, "reviewer", "reviewer-password")
    visible_projects = client.get("/api/projects", headers=member_headers)

    assert visible_projects.status_code == 200
    assert visible_projects.json() == [{"project_id": "alpha", "role": "viewer"}]


def test_members_cannot_manage_projects_or_view_unassigned_projects(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": "reviewer", "password": "reviewer-password"},
    )
    client.post("/api/admin/projects", headers=admin_headers, json={"project_id": "alpha"})

    member_headers = login(client, "reviewer", "reviewer-password")
    denied = client.post("/api/admin/projects", headers=member_headers, json={"project_id": "secret"})
    visible_projects = client.get("/api/projects", headers=member_headers)

    assert denied.status_code == 403
    assert visible_projects.json() == []
