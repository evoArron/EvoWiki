# EvoWiki

> An AI-Native R&D brain based on Karpathy's LLM Wiki methodology and Model Context Protocol (MCP). Features an asset-decoupled Agentic RAG architecture with targeted contextual annotations, threaded human-in-the-loop alignment, and git-powered time travel.

[中文文档](README.zh-CN.md) | [Product specification](docs/%E4%BC%81%E4%B8%9A%E7%BA%A7%20AI%20%E7%A0%94%E5%8F%91%E6%96%87%E6%A1%A3%E4%B8%AD%E6%9E%A2%E8%A7%84%E6%A0%BC%E8%AF%B4%E6%98%8E%E4%B9%A6.md)

EvoWiki is an AI-native documentation hub for engineering organizations. It treats a single Git repository as the source of truth for documentation, keeps access control and annotations in a local SQLite database, and exposes focused, clean context to AI agents through MCP.

> **Status: specification and repository setup.** The implementation described below is planned; the application is not yet available to run.

## Why EvoWiki

Engineering knowledge usually ends up split between code repositories, documents, chats, and AI conversations. EvoWiki is designed to make documentation durable, reviewable, and useful to both people and agents:

- Keep clean Markdown documentation in one versioned enterprise repository.
- Organize knowledge by project while mounting shared project documentation through declared dependencies.
- Store identity, project ACLs, and threaded annotations in one local SQLite file.
- Keep comments and highlights out of Markdown so the main branch stays readable.
- Let people explicitly control when file changes are committed, pushed, and indexed.
- Provide Git-backed history and diffs for documentation changes.

## Architecture

```text
EvoWiki repository
├── mcp-server/             FastAPI service and MCP tools
│   ├── app/
│   │   ├── api/            REST endpoints
│   │   ├── database/       SQLite models: users, permissions, comments
│   │   ├── mcp/            Agent read/write tools
│   │   ├── services/       MarkItDown, Git, and indexing services
│   │   └── websocket/      Project-scoped REFRESH broadcasts
│   └── evowiki.db          Local SQLite database
├── web-portal/             React + Vite + TypeScript portal
└── enterprise-wiki-repo/   Versioned enterprise documentation repository
    ├── global-shared/docs/
    └── <project>/
        ├── meta.json
        ├── docs/
        ├── .attachments/
        └── .history/
```

The application service and the documentation repository have separate responsibilities: Git stores the clean documentation assets, while SQLite holds operational data that must not alter those assets.

## Core Workflows

### Ingest and review documents

Office and PDF uploads are retained under a project's `.attachments/` directory. The backend converts them to Markdown with [MarkItDown](https://github.com/microsoft/markitdown); spreadsheets are normalized before conversion. The portal presents the original file and generated Markdown side by side so a person can correct the result before it becomes documentation.

### Browse project knowledge

Each project declares shared knowledge sources in `meta.json`:

```json
{
  "project_name": "EvoWiki-Demo-Project",
  "description": "An example engineering knowledge hub",
  "dependencies": ["global-shared", "common-payment-spec"]
}
```

The portal lazily loads the document tree. Mounted dependency folders are displayed as linked content, while access checks remain project-scoped.

### Discuss without polluting Markdown

Text selections create threaded comments stored in SQLite. Each comment stores an immutable source-text anchor and its discussion thread. During rendering, matching text is highlighted in the UI only; no comment data or highlight markup is written to the Markdown file.

For an agent request, MCP supplies only the selected source text and its annotations. When a change resolves a comment, the prior file version is archived under `.history/` and the SQLite comment is marked resolved.

### Sync and index deliberately

The portal's **Update and Sync Index** action runs one blocking, serial workflow:

1. Persist approved file changes.
2. Aggregate changes into a Conventional Commits-style Git commit and push it.
3. Refresh the local ChromaDB index.

The UI stays in a loading state until the workflow completes. WebSocket messages carry only a `REFRESH` signal; clients debounce and replace their full document view rather than consuming streamed document text.

## Security and Data Boundaries

- **SQLite only:** `evowiki.db` contains users, project permissions, and comments. No external relational database is required.
- **Path sandboxing:** every file access must resolve an absolute path and verify it with `os.path.commonpath` against the authorized project root.
- **Project ACLs:** authenticated users and agents receive access only to permitted project directories.
- **Clean Markdown:** annotations, threads, and selection snapshots are persisted in SQLite, never embedded in document files.
- **Focused MCP context:** agents receive clean source text plus relevant annotations, not an uncontrolled full-document comment payload.

## Planned Technology

| Area | Technology |
| --- | --- |
| Backend | Python, FastAPI, SQLAlchemy, SQLite |
| Frontend | React 18, Vite, TypeScript, Ant Design, Tailwind CSS |
| Markdown | `react-markdown`, `remark-gfm` |
| Diagrams | `react-mermaid`, `mermaid`, rendered only after manual expansion |
| History | Git and `react-diff-viewer-next` |
| Conversion | Microsoft MarkItDown |
| Indexing | Local ChromaDB |

## Development Roadmap

1. Bootstrap the FastAPI server and React portal monorepo.
2. Add SQLite models and project-path authorization middleware.
3. Implement upload conversion and lazy document-tree APIs.
4. Implement the serial sync-and-index endpoint.

Detailed requirements are maintained in the [product specification](docs/%E4%BC%81%E4%B8%9A%E7%BA%A7%20AI%20%E7%A0%94%E5%8F%91%E6%96%87%E6%A1%A3%E4%B8%AD%E6%9E%A2%E8%A7%84%E6%A0%BC%E8%AF%B4%E6%98%8E%E4%B9%A6.md).

## Contributing

The project is in its initial setup stage. Before contributing implementation work, follow the constraints in [AGENTS.md](AGENTS.md), especially the SQLite-only persistence model, path-traversal protection, clean-Markdown rule, and non-streaming refresh model.

## License

Distributed under the [MIT License](LICENSE).
