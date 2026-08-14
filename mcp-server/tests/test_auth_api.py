import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def create_test_app(tmp_path):
    return create_app(
        database_path=tmp_path / "evowiki.db",
        database_root=tmp_path,
        jwt_secret="test-secret",
        initial_admin_username="admin",
        initial_admin_password="correct-horse-battery-staple",
    )


def test_admin_can_log_in_and_read_current_identity(tmp_path):
    client = TestClient(create_test_app(tmp_path))

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )

    assert login.status_code == 200
    token = login.json()["access_token"]

    current_user = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert current_user.status_code == 200
    assert current_user.json() == {"username": "admin", "role": "admin"}


def test_invalid_or_missing_credentials_are_rejected(tmp_path):
    client = TestClient(create_test_app(tmp_path))

    invalid_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    overlong_password = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "x" * 73},
    )
    missing_token = client.get("/api/auth/me")
    tampered_token = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})

    assert invalid_login.status_code == 401
    assert overlong_password.status_code == 401
    assert missing_token.status_code == 401
    assert tampered_token.status_code == 401


def test_database_file_must_stay_inside_database_root(tmp_path):
    with pytest.raises(ValueError, match="数据库文件必须位于服务目录"):
        create_app(
            database_path=tmp_path.parent / "evowiki.db",
            database_root=tmp_path,
            jwt_secret="test-secret",
            initial_admin_username="admin",
            initial_admin_password="correct-horse-battery-staple",
        )
