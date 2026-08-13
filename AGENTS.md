# ⚙️ EvoWiki Core AI Skill Specification (Matt's Style)

你正在使用 Pi Harness 参与 Evolight 团队的 EvoWiki 项目开发。
你必须严格遵守以下串行步骤和技术边界，严禁进行任何过度设计（Over-engineering）。

## 🛡️ 1. 核心技术边界 (Strict Boundaries)
*   **持久化层**：绝对禁止引入 MySQL/PostgreSQL。本地仅允许使用单文件 `evowiki.db` (SQLite) + 物理文件路径。
*   **安全防线**：任何文件写入必须使用 `os.path.commonpath` 比对绝对路径，强行拦截路径穿越。
*   **前端同步**：拒绝打字机与流式推流。WebSocket 仅发送 `REFRESH` 信号，前端执行全量覆盖刷新。
*   **数据隔离**：飞书评论数据和高亮原文绝对禁止写入 Markdown，统一存入 SQLite 评论表。MCP 仅投喂纯净的【原文+批注】。

## 🏃‍♂️ 2. 任务执行序列 (Execution Sequence)

### [STEP 1]: 基础单体 Monorepo 基建初始化
*   在根目录下初始化 `mcp-server/` (FastAPI) 与 `web-portal/` (React + Vite + TypeScript)。
*   创建前端 `package.json`，必须严格锁定 PRD 第 4 章声明的 `react-markdown`、`react-mermaid` 及 `react-diff-viewer-next` 依赖。

### [STEP 2]: SQLite 数据库与安全中间件搭建
*   使用 SQLAlchemy 建立 `users`、`project_permissions`、`comments` 三张最简表。
*   编写 FastAPI 的全局文件访问中间件，实施沙箱路径强校验。

### [STEP 3]: 引入微软 MarkItDown 与本地文件路由
*   编写 `/api/upload` 接口。引入 `markitdown` 库，实现本地 Office/PDF 的零成本纯文本转换。
*   编写递归扫描接口，返回符合前端 `EvoWikiTreeNode` 接口规范的 JSON 树。

### [STEP 4]: 串行手动同步端点
*   编写 `/api/sync-index` 接口。接收前端一键触发信号，纯串行阻塞执行：本地落盘 ➡️ 聚合 Commit 写入 ➡️ 触发 Git Push ➡️ 刷新本地 ChromaDB 索引。

## 🚨 3. 前端编译与类型卡准 (TSX Rules)
*   所有组件必须使用 TypeScript (TSX)。
*   在编写侧边树时，必须实现懒加载（Lazy Load），且将依赖挂载目录的节点图标强制替换为 🔗。
*   Mermaid 渲染必须包裹在 `<details>` 折叠占位符内，由人类点击后被动激活，严禁高频自动重绘。
