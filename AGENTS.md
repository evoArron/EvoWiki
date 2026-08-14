# ⚙️ EvoWiki Core AI Skill Specification (Matt's Style)

你正在使用 Pi Harness 参与 Evolight 团队的 EvoWiki 项目开发。
你必须严格遵守以下串行步骤和技术边界，严禁进行任何过度设计（Over-engineering）。

## 🛡️ 1. 核心技术边界 (Strict Boundaries)
*   **持久化层**：绝对禁止引入 MySQL/PostgreSQL。本地仅允许使用单文件 `evowiki.db` (SQLite) + 物理文件路径。
*   **安全防线**：任何文件写入必须使用 `os.path.commonpath` 比对绝对路径，强行拦截路径穿越。
*   **前端同步**：拒绝打字机与流式推流。WebSocket 仅发送 `REFRESH` 信号，前端执行全量覆盖刷新。
*   **数据隔离**：飞书评论数据和高亮原文绝对禁止写入 Markdown，统一存入 SQLite 评论表。MCP 仅投喂纯净的【原文+批注】。
*   **文档语言**：新增或修改的项目文档使用中文撰写；技术专有名词、命令、标识符和代码可保留原文。

## 🔎 GitNexus 强制工作流
*   **GitNexus CLI 必须执行**：每个涉及代码理解、调试、影响评估、重构或提交的任务，先运行 `gitnexus status`；索引缺失或过期时运行 `gitnexus analyze`。
*   **代码导航必须基于索引**：分别使用 `gitnexus query`、`gitnexus context`、`gitnexus impact` 和 `gitnexus detect-changes` 完成调用链定位、符号上下文、改动影响与提交前范围校验；代码提交后刷新索引。

## 🏃‍♂️ 2. 任务执行序列 (Execution Sequence)

### [STEP 1]: 基础单体 Monorepo 基建初始化
*   在根目录下初始化 `mcp-server/` (FastAPI) 与 `web-portal/` (React + Vite + TypeScript)。
*   创建前端 `package.json`，必须严格锁定 PRD 第 4 章声明的 `react-markdown`、`react-mermaid` 及 `react-diff-viewer-next` 依赖。

### [STEP 2]: SQLite 数据库与安全中间件搭建
*   使用 SQLAlchemy 建立 `users`、`project_permissions`、`comments` 三张最简表。
*   编写 FastAPI 的全局文件访问中间件，实施沙箱路径强校验。

### [STEP 3]: Markdown 上传、MCP 草稿与本地文件路由
*   编写 `/api/upload` 接口。MVP 只接受 `.md` 文件，校验项目 ACL、扩展名和安全路径。人类上传的确认文件写入项目 `docs/`；MCP 上传的内容写入项目 `.drafts/`，状态为待核对。
*   MCP 草稿绝不触发 Git 提交、Push 或 Raw RAG 索引。人类在网页预览、可做纯文本修订后，显式发布到 `docs/`。
*   编写递归扫描接口，返回符合前端 `EvoWikiTreeNode` 接口规范的 JSON 树。
*   Office/PDF/Excel 转换、MarkItDown、附件留底和双栏校对属于后续版本，不在 MVP 实现。

### [STEP 4]: Markdown 发布与原文索引
*   编写 `/api/sync-index` 接口。接收人类确认发布的 Markdown 或失败重试，纯串行执行：精确路径 `git add` ➡️ 单文件 Commit ➡️ Git Push ➡️ 刷新该文件的 Raw RAG ChromaDB 索引。
*   返回 Git commit 与索引状态。MVP 不聚合跨项目变更，不编译 LLM Wiki，不执行 reranking。

## 🚨 3. 前端编译与类型卡准 (TSX Rules)
*   所有组件必须使用 TypeScript (TSX)。
*   在编写侧边树时，必须实现懒加载（Lazy Load），且将依赖挂载目录的节点图标强制替换为 🔗。
*   Mermaid 渲染必须包裹在 `<details>` 折叠占位符内，由人类点击后被动激活，严禁高频自动重绘。

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **EvoWiki** (509 symbols, 1902 relationships, 44 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/EvoWiki/context` | Codebase overview, check index freshness |
| `gitnexus://repo/EvoWiki/clusters` | All functional areas |
| `gitnexus://repo/EvoWiki/processes` | All execution flows |
| `gitnexus://repo/EvoWiki/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
