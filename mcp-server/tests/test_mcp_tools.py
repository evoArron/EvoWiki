import asyncio

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from app.publishing import ChromaIndexer
from test_draft_api import create_editor, create_test_app, login


def test_mcp_reads_and_searches_only_indexed_documents_in_authorized_projects(tmp_path):
    indexer = ChromaIndexer(tmp_path / "chroma")
    git_runner = lambda arguments, _: "commit-1\n" if arguments == ["rev-parse", "HEAD"] else ""
    client, _ = create_test_app(tmp_path, git_runner=git_runner, indexer=indexer)
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    editor_headers = create_editor(client, admin_headers)
    token = editor_headers["Authorization"].removeprefix("Bearer ")
    draft = client.post("/api/projects/alpha/drafts", headers=editor_headers, json={"path": "mcp.md", "content": "# Architecture\nMCP retrieval source"}).json()
    client.post(f"/api/projects/alpha/drafts/{draft['id']}/publish", headers=editor_headers, json={"target_path": "mcp.md"})

    _, document = asyncio.run(client.app.state.mcp.call_tool("read_published_document", {"access_token": token, "project_id": "alpha", "path": "docs/mcp.md"}))
    _, results = asyncio.run(client.app.state.mcp.call_tool("search_published_documents", {"access_token": token, "query": "retrieval", "project_ids": ["alpha"]}))

    assert document == {"path": "alpha/docs/mcp.md", "content": "# Architecture\nMCP retrieval source", "git_commit": "commit-1"}
    assert results["result"] and results["result"][0]["path"] == "alpha/docs/mcp.md"


def test_mcp_rejects_unpublished_documents_and_unassigned_projects(tmp_path):
    client, _ = create_test_app(tmp_path)
    admin_headers = login(client, "admin", "correct-horse-battery-staple")
    editor_headers = create_editor(client, admin_headers)
    token = editor_headers["Authorization"].removeprefix("Bearer ")

    with pytest.raises(ToolError, match="尚未发布"):
        asyncio.run(client.app.state.mcp.call_tool("read_published_document", {"access_token": token, "project_id": "alpha", "path": "docs/missing.md"}))
