from fastapi.testclient import TestClient

from conftest import ADMIN_PASSWORD, bearer, create_test_app, login


def test_admin_can_configure_and_test_the_document_git_repository(tmp_path):
    calls = []
    def git_runner(arguments, _):
        calls.append(arguments)
        if arguments in (["rev-parse", "--is-inside-work-tree"], ["remote", "set-url", "origin", "git@github.com:example/docs.git"]):
            raise RuntimeError("not configured")
        return ""

    client = TestClient(create_test_app(tmp_path, git_runner=git_runner))
    headers = bearer(login(client, "admin", ADMIN_PASSWORD))
    configured = client.put("/api/admin/git-settings", headers=headers, json={"remote_url": "git@github.com:example/docs.git", "author_name": "EvoWiki", "author_email": "docs@example.com"})
    tested = client.post("/api/admin/git-settings/test", headers=headers)

    assert configured.json() == {"remote_url": "git@github.com:example/docs.git", "author_name": "EvoWiki", "author_email": "docs@example.com", "configured": True}
    assert tested.status_code == 204
    assert ["init", "-b", "main"] in calls
    assert ["remote", "add", "origin", "git@github.com:example/docs.git"] in calls
    assert ["ls-remote", "--heads", "origin"] in calls


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
