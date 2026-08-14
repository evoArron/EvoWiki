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


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_member_must_change_temporary_password_before_using_workspace(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_token = login(client, "admin", "correct-horse-battery-staple")

    created = client.post(
        "/api/admin/members",
        headers=bearer(admin_token),
        json={"username": "reviewer", "display_name": "Review User"},
    )
    member_token = login(client, "reviewer", created.json()["temporary_password"])
    blocked = client.get("/api/projects", headers=bearer(member_token))
    changed = client.post(
        "/api/auth/change-password",
        headers=bearer(member_token),
        json={"current_password": created.json()["temporary_password"], "new_password": "new-password"},
    )
    refreshed_token = login(client, "reviewer", "new-password")

    assert created.status_code == 201
    assert created.json()["must_change_password"] is True
    assert blocked.status_code == 403
    assert changed.status_code == 204
    assert client.get("/api/projects", headers=bearer(refreshed_token)).status_code == 200


def test_password_reset_invalidates_old_token_and_audit_is_redacted(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_token = login(client, "admin", "correct-horse-battery-staple")
    created = client.post(
        "/api/admin/members",
        headers=bearer(admin_token),
        json={"username": "reviewer", "display_name": "Review User"},
    )
    member_token = login(client, "reviewer", created.json()["temporary_password"])

    reset = client.post(
        "/api/admin/members/reviewer/reset-password",
        headers=bearer(admin_token),
        json={"password": "replacement-password"},
    )
    old_token = client.get("/api/auth/me", headers=bearer(member_token))
    audit = client.get("/api/admin/audit-logs", headers=bearer(admin_token))

    assert reset.status_code == 204
    assert old_token.status_code == 401
    assert all("replacement-password" not in str(entry) for entry in audit.json()["items"])
    assert any(entry["action"] == "member.password_reset" for entry in audit.json()["items"])


def test_project_owner_is_project_admin_and_archived_projects_reject_permission_changes(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_token = login(client, "admin", "correct-horse-battery-staple")
    created = client.post(
        "/api/admin/members",
        headers=bearer(admin_token),
        json={"username": "owner", "display_name": "Project Owner"},
    )
    owner_token = login(client, "owner", created.json()["temporary_password"])
    client.post(
        "/api/auth/change-password",
        headers=bearer(owner_token),
        json={"current_password": created.json()["temporary_password"], "new_password": "owner-password"},
    )
    client.post(
        "/api/admin/projects",
        headers=bearer(admin_token),
        json={"project_id": "alpha", "name": "Alpha", "owner_username": "owner"},
    )
    permissions = client.get("/api/admin/projects/alpha/permissions", headers=bearer(login(client, "owner", "owner-password")))
    archived = client.post("/api/admin/projects/alpha/archive", headers=bearer(admin_token))
    denied = client.post(
        "/api/admin/projects/alpha/permissions",
        headers=bearer(login(client, "owner", "owner-password")),
        json={"username": "owner", "role": "project_admin"},
    )

    assert permissions.status_code == 200
    assert permissions.json() == [{"username": "owner", "display_name": "Project Owner", "role": "project_admin"}]
    assert archived.status_code == 200
    assert denied.status_code == 403


def test_project_archive_and_restore_reject_repeated_transitions_without_audit(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_token = login(client, "admin", "correct-horse-battery-staple")
    headers = bearer(admin_token)
    client.post("/api/admin/projects", headers=headers, json={"project_id": "alpha", "name": "Alpha"})

    assert client.post("/api/admin/projects/alpha/archive", headers=headers).status_code == 200
    audit_total = client.get("/api/admin/audit-logs", headers=headers).json()["total"]
    repeated_archive = client.post("/api/admin/projects/alpha/archive", headers=headers)
    repeated_restore = client.post("/api/admin/projects/alpha/restore", headers=headers)

    assert repeated_archive.status_code == 409
    assert repeated_restore.status_code == 200
    assert client.post("/api/admin/projects/alpha/restore", headers=headers).status_code == 409
    assert client.get("/api/admin/audit-logs", headers=headers).json()["total"] == audit_total + 1


def test_project_permission_put_uses_path_member_identity(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_token = login(client, "admin", "correct-horse-battery-staple")
    client.post(
        "/api/admin/members",
        headers=bearer(admin_token),
        json={"username": "editor", "display_name": "Editor", "password": "temporary-password"},
    )
    client.post("/api/admin/projects", headers=bearer(admin_token), json={"project_id": "alpha", "name": "Alpha"})

    response = client.put(
        "/api/admin/projects/alpha/permissions/editor",
        headers=bearer(admin_token),
        json={"role": "editor"},
    )

    assert response.status_code == 200
    assert response.json() == {"username": "editor", "display_name": "Editor", "role": "editor"}


def test_last_system_admin_cannot_be_disabled(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_token = login(client, "admin", "correct-horse-battery-staple")

    response = client.post("/api/admin/members/admin/status", headers=bearer(admin_token), json={"is_active": False})

    assert response.status_code == 409


def test_active_project_owner_cannot_be_disabled_before_transfer_or_archive(tmp_path):
    client = TestClient(create_test_app(tmp_path))
    admin_token = login(client, "admin", "correct-horse-battery-staple")
    client.post(
        "/api/admin/members",
        headers=bearer(admin_token),
        json={"username": "owner", "display_name": "Project Owner", "password": "temporary-password"},
    )
    client.post(
        "/api/admin/projects",
        headers=bearer(admin_token),
        json={"project_id": "alpha", "name": "Alpha", "owner_username": "owner"},
    )

    response = client.post("/api/admin/members/owner/status", headers=bearer(admin_token), json={"is_active": False})

    assert response.status_code == 409
