import subprocess

from app.publishing import run_git
from test_draft_api import create_editor, create_test_app, login


def command(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def test_publish_creates_one_file_commit_and_pushes_to_a_local_remote(tmp_path):
    repository = tmp_path / "enterprise-wiki-repo"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    command("git", "init", "-b", "main", cwd=repository)
    command("git", "config", "user.email", "tests@example.invalid", cwd=repository)
    command("git", "config", "user.name", "Tests", cwd=repository)
    command("git", "init", "--bare", str(remote), cwd=tmp_path)
    command("git", "remote", "add", "origin", str(remote), cwd=repository)
    command("git", "commit", "--allow-empty", "-m", "initial", cwd=repository)
    command("git", "push", "-u", "origin", "main", cwd=repository)

    client, indexed = create_test_app(tmp_path, git_runner=run_git)
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    editor_headers = create_editor(client, admin_headers)
    draft = client.post("/api/projects/alpha/drafts", headers=editor_headers, json={"path": "draft.md", "content": "# Published"}).json()
    result = client.post(f"/api/projects/alpha/drafts/{draft['id']}/publish", headers=editor_headers, json={"target_path": "published.md"})

    assert result.status_code == 200
    assert result.json()["status"] == "indexed"
    assert command_output("git", "show", "--name-only", "--format=", "HEAD", cwd=repository) == "alpha/docs/published.md\n"
    assert command_output("git", "rev-parse", "origin/main", cwd=repository).strip() == result.json()["git_commit"]
    assert indexed == [("alpha", "alpha/docs/published.md", "# Published", result.json()["git_commit"])]


def command_output(*args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout
