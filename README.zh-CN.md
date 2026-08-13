# EvoWiki

[English](README.md) | [产品规格说明](docs/企业级%20AI%20研发文档中枢规格说明书.md)

EvoWiki 是面向研发团队的 AI Native 文档中枢。它以单一 Git 文档仓库作为事实来源，将访问控制与批注存入本地 SQLite，并通过 MCP 向 AI Agent 提供聚焦、干净的上下文。

> **状态：规格与仓库初始化阶段。** 以下能力均为已确定的实现目标，当前应用尚不可运行。

## 项目目标

研发知识往往分散在代码仓库、文档、聊天记录和 AI 对话中。EvoWiki 旨在让文档资产可沉淀、可审计，并同时服务于人类与 AI：

- 用一个可版本化的企业 Git 仓库存放干净的 Markdown 文档。
- 按项目组织知识，并通过显式依赖挂载共享项目文档。
- 用单一 SQLite 文件存放身份、项目 ACL 与盖楼评论。
- 将评论和高亮与 Markdown 主干隔离，保持文档可读、可审计。
- 由人类显式控制文件提交、推送与索引建立的时机。
- 使用 Git 历史与差异对比追溯文档演进。

## 架构

```text
EvoWiki 仓库
├── mcp-server/             FastAPI 服务与 MCP 工具
│   ├── app/
│   │   ├── api/            REST 接口
│   │   ├── database/       SQLite 模型：用户、权限、评论
│   │   ├── mcp/            Agent 读写工具
│   │   ├── services/       MarkItDown、Git 与索引服务
│   │   └── websocket/      按项目广播 REFRESH 信号
│   └── evowiki.db          本地 SQLite 数据库
├── web-portal/             React + Vite + TypeScript 门户
└── enterprise-wiki-repo/   受版本控制的企业文档仓库
    ├── global-shared/docs/
    └── <project>/
        ├── meta.json
        ├── docs/
        ├── .attachments/
        └── .history/
```

应用服务与文档资产仓库职责分离：Git 存放干净的文档资产；SQLite 保存不应修改这些资产的运行数据。

## 核心流程

### 文档入库与人工校对

Office 和 PDF 上传文件保存在项目的 `.attachments/` 目录。后端通过 [MarkItDown](https://github.com/microsoft/markitdown) 转换为 Markdown；Excel 会在转换前进行结构规范化。门户提供原件与 Markdown 双栏对照，人工确认和修正后再写入正式文档。

### 项目知识浏览

每个项目通过 `meta.json` 声明共享知识依赖：

```json
{
  "project_name": "EvoWiki-Demo-Project",
  "description": "Evolight 团队的 AI 研发资产中枢示例",
  "dependencies": ["global-shared", "common-payment-spec"]
}
```

门户按需懒加载文档树。依赖挂载目录以链接内容展示，但访问校验始终以项目范围为边界。

### 不污染 Markdown 的讨论

用户划词后创建的评论线程统一存入 SQLite。每条评论保存不可变的原文锚点与讨论内容；前端仅在渲染时动态高亮匹配的文本，不会向 Markdown 写入评论数据或高亮标签。

MCP 只向 Agent 提供被选中的原文和对应批注。修改解决评论后，系统将旧文件归档到 `.history/`，并将 SQLite 中的评论标记为已解决。

### 显式同步与建索引

门户中的 **更新并同步索引** 操作按单线程串行方式执行：

1. 落盘已确认的文件修改。
2. 聚合变更，生成符合 Conventional Commits 的 Git 提交并推送。
3. 刷新本地 ChromaDB 索引。

执行期间界面保持加载状态。WebSocket 仅发送 `REFRESH` 信号；前端防抖后完整替换文档视图，不接收流式文档文本。

## 安全与数据边界

- **仅使用 SQLite：** `evowiki.db` 保存用户、项目权限和评论，无需外部关系型数据库。
- **路径沙箱：** 每次文件访问都必须解析绝对路径，并通过 `os.path.commonpath` 对授权项目根目录进行校验。
- **项目 ACL：** 已认证用户和 Agent 只能访问其获授权的项目目录。
- **Markdown 保持干净：** 批注、讨论和选区快照仅存入 SQLite，绝不写入文档文件。
- **MCP 精准投喂：** Agent 接收干净原文及相关批注，而不是不受约束的整篇评论文档。

## 计划技术栈

| 范畴 | 技术 |
| --- | --- |
| 后端 | Python、FastAPI、SQLAlchemy、SQLite |
| 前端 | React 18、Vite、TypeScript、Ant Design、Tailwind CSS |
| Markdown | `react-markdown`、`remark-gfm` |
| 图表 | `react-mermaid`、`mermaid`，仅在人工展开后渲染 |
| 历史对比 | Git 与 `react-diff-viewer-next` |
| 文件转换 | Microsoft MarkItDown |
| 索引 | 本地 ChromaDB |

## 开发路线

1. 初始化 FastAPI 服务与 React 门户 Monorepo。
2. 建立 SQLite 模型与项目路径鉴权中间件。
3. 实现上传转换和懒加载文档树接口。
4. 实现串行同步与索引端点。

详细需求请参阅[产品规格说明](docs/企业级%20AI%20研发文档中枢规格说明书.md)。

## 贡献

项目仍处于初始化阶段。参与实现前请遵循 [AGENTS.md](AGENTS.md) 中的约束，尤其是仅 SQLite 持久化、路径穿越防护、Markdown 主干无批注，以及非流式全量刷新规则。

## 许可证

本项目基于 [MIT License](LICENSE) 发布。
