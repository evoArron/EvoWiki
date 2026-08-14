# 🚀 EvoWiki: 企业级 AI 研发文档中枢规格说明书 (PRD 全量完备版)

## 📌 1. 项目定位与核心产品定义
**EvoWiki** 是由 **Evolight** 团队推出的企业级、AI Native 研发思维与文档中枢。系统采用“知识与代码彻底物理解耦”的设计，底层基于【单一企业大 Git 文档仓库 + 本地轻量 SQLite 鉴权】的双轨架构。通过多项目子目录平铺、一键手动索引控制、飞书级“划词盖楼评论”和“时光机版本回溯”，以最短路径实现企业全量技术资产的自我生长与绝对安全审计。

### 核心设计原则 (Core Principles)
*   **Single-Repo-as-a-DB**：全公司仅需托管一个唯一的 Git 文档大仓库（可托管于自建 GitLab、GitHub、Gitee 或腾讯云 CNB）。零重型外部数据库依赖。
*   **SQLite 安全沙箱**：引入轻量单文件 SQLite，专门用于存放用户体系、项目 ACL 权限以及飞书评论数据，彻底免疫路径穿越与横向越权漏洞。
*   **手动控制，消除时差**：拒绝复杂的自动合并与异步双轨检索。引入网页端【更新并建立索引】实体按钮，由人类显式控制资产的沉淀与向量化，用最确定性的串行流程换取绝对的语义精准。
*   **真理在主干，碰撞在历史**：文档主干始终保持绝对干净，划词评论数据剥离至 SQLite 中，大模型通过 MCP 仅读取净化后的特定上下文，杜绝长上下文“旧记忆污染”。

### MVP 范围（优先级高于后续模块细节）
本说明书保留完整产品愿景；若后文模块与本节冲突，以本节作为 MVP 的实现边界。

*   **输入**：仅接受 Markdown 文件。人类确认的文件可发布；MCP 可上传 Markdown 草稿，必须经人类核对后才可发布。Office/PDF/Excel 转换、MarkItDown、附件留底、双栏校对和 Git LFS 后置。
*   **知识源**：项目相互隔离；不做依赖挂载、跨项目检索或跨项目树展示。
*   **发布与检索**：MCP 草稿保存于项目 `.drafts/`，不进入 Git 或 RAG。人类确认发布后，服务串行完成 Git commit、Git push 和 Raw RAG 索引。MCP 可读取已索引原文，并返回来源路径与 Git commit。
*   **暂不交付**：Markdown 协同编辑、复杂草稿工作流、划词评论、WebSocket 通知、Git 时光机、MCP 直接发布、LLM Wiki 编译、reranking、模型配置 UI、长文档自动拆分和跨文档综合 Wiki。
*   **保留的安全底线**：SQLite 用户与项目 ACL、JWT、`os.path.commonpath` 文件沙箱，以及全量覆盖式前端刷新策略。
*   **后续规划**：已确认后置能力及其进入条件统一记录于[产品路线图](EvoWiki-产品路线图.md)。

---

## 🏗️ 2. 全局物理文件与数据架构 (Monorepo)
企业的唯一大文档 Git 仓库被拉取（Clone）到服务器后，整体物理与逻辑结构如下：

```text
evowiki/
├── mcp-server/             # 后端服务核心 (FastAPI 引擎)
│   ├── app/
│   │   ├── database/       # SQLite 数据库模型与轻量 ORM 逻辑 (用户、权限、评论表)
│   │   ├── api/            # 统一大后台 RESTful API 路由
│   │   ├── mcp/            # MCP 协议工具箱 (响应 IDE 端大模型的 Tools 读写请求)
│   │   ├── websocket/      # WebSocket 房间广播 (按项目 ID 进行房间流隔离广播)
│   │   └── services/       # 微软 MarkItDown 解析、全局 Git 节流聚合服务
│   ├── evowiki.db          # 【轻量 SQLite 单文件数据库】
│   └── main.py
├── web-portal/             # 前端大后台 (React/Vite + TypeScript + Tailwind + AntD/Shadcn)
│   ├── src/
│   │   ├── components/     # React-Mermaid 渲染器、飞书式评论组件、时光机面板、权限配置
│   │   └── App.tsx
└── enterprise-wiki-repo/   # 【核心资产：全公司唯一的、挂载了 Git 远程端的大文档仓库】
    ├── .git/               # 整个企业文档库的统一 Git 节点 (支持 Push 到 CNB/GitHub 等)
    ├── global-shared/      # 全局公共知识库 (公司统一开发规范、UI规范，供多项目多路挂载)
    │   └── docs/
    ├── project-alpha/      # 项目 A 的专属子目录
    │   ├── meta.json       # 项目元数据：含本子项目特定依赖多路挂载配置
    │   └── docs/           # 干净的最新版 Markdown 主干 (无任何 HTML 标签或评论污染)
    └── project-beta/       # 项目 B 的专属子目录
        ├── meta.json
        ├── docs/
        └── .attachments/   # 隐藏的原始附件夹 (存放用户上传的 Word/Excel/PDF 原件)
```

---

## 🛠️ 3. 核心功能模块规格详情

### 模块 A：基于 SQLite 的企业级沙箱权限控制 (SQLite Auth & ACL)
1.  **静态用户与权限表**：SQLite 数据库中建立 `users`（用户表，存放 Bcrypt 密码哈希）与 `project_permissions` (项目权限表，存放用户与项目子目录的内聚映射关系)。人类用户与 AI 智能体账户登录统一换取 JWT 令牌。
2.  **绝对路径防护**：后端 FastAPI 实施最高级别的路径沙箱审计。接收到前端请求或 MCP 调用时，中间件实时解析 JWT 身份，并去 SQLite 中比对当前用户对该项目子目录是否拥有合法权限。
3.  **阻断越权**：校验失败立刻阻断文件流。一旦通过，后端在代码中强行绑定物理安全路径（如 `os.path.join(BASE_DIR, project_id)`），黑客和产生幻觉的大模型绝无可能跨出项目边界触碰底层 Linux 操作系统文件。

### 模块 B：多模态入库双栏对照与人类纠错 (Ingestion Pipeline)
1.  **文件留底**：用户上传 Word/Excel/PDF，后端冷备原件至当前项目子目录下的隐藏文件夹 `.attachments/`（供人类随时下载对照）。
2.  **本地快速解析**：调用**微软开源的 `MarkItDown` 库**进行秒级本地纯文本/表格结构提取。针对 Excel 重灾区，后端强制先由 Pandas 规范化清洗为标准的 HTML Table 再转为标准的 Markdown Table，防止格式崩塌。
3.  **AI 视觉语义注入**：若文档含图片，自动异步调用低成本多模态模型进行“图译文”，将图片语义翻译为纯文本，以 `<!-- AI_VISION_DESCRIPTIONS_START -->` 的 HTML 注释形式**原地注入**到生成的 Markdown 文件中。
4.  **人类反向纠错流**：前端大后台采用双栏对照（Split View）：左栏预览原件，右栏提供转化后的 Markdown 编辑器。人类用户进行肉眼微调和反向纠错，确保源数据 100% 精准后，点击“确认入库”。

### 模块 C：多项目多路动态挂载 (Many-to-Many Mappings)
1.  **依赖配置**：在各项目的 `meta.json` 中配置 `dependencies` 数组（例如项目 A、B 共享支付规范，项目 B、C 共享大数据规范）。
2.  **多路并行扫描**：当大模型调用 MCP 进行语义检索或人类在大后台查阅该项目时，后端服务根据依赖配置执行**多路并行路径扫描**：`当前项目子目录 docs/` + `所有依赖项目子目录的 docs/`。
3.  **前端挂载呈现**：前端大后台的左侧树状目录动态挂载这些跨项目共享的知识夹，图标统一强制替换为 `LinkOutlined` 🔗。

### 模块 D：飞书式划词评论与极简 MCP 靶向对齐 (Contextual Thread & MCP)
1.  **数据与文件分离**：人类在大后台划选文本发表评论。支持多用户、多模型在气泡内进行多条盖楼回复（Thread 模式）。所有的评论内容、楼层数据和选中的“原文快照”**统一存入 SQLite 评论表中，不再污染、不修改底层的 Markdown 物理文件**。
2.  **MCP 极简投喂**：当大模型在 IDE 里通过 MCP 触发检索和修改指令时，系统绝对不投喂带有各种复杂 UUID 的整篇长文档。MCP 接口通过简单的字符串拼接，只向大模型输出最干净的 **【当前划词原文 + 人类批注内容】**。
3.  **大模型消费与一键净化**：大模型凭借其长上下文记忆，靶向重写受影响的代码片段，并通过 MCP 工具将修改后的短文本返回。后端程序接收后自动更新磁盘文件，并将原含有高亮评论的旧文件打包推入该项目子目录下的 `.history/` 时光机，最后将 SQLite 中该条评论的状态标记为“已解决（Resolved）”。

### 模块 E：【一键同步并建立索引】实体控制流 (The Indexing Button)
1.  ** Loading 状态拦截**：当前端人类完成反向纠错、或在网页上发表/解决完飞书批注后，点击网页顶部的 **【更新并同步索引】** 按钮。前端界面进入全量 Loading 状态，进度条常驻，提示“AI 正在重塑知识库，在此期间请勿启动代码 Agent 检索”。
2.  **纯串行阻塞同步**：后端 FastAPI 接收到请求后，以最简单的**纯串行单线程阻塞方式**顺序执行：
    *   **第一步**：对该项目子目录更新本地文件系统。
    *   **第二步（模块 F：Commit摘要聚合器）**：系统自动收集本次更新的所有修改日志（哪个模型/用户、改了哪个子项目、改了什么文件），根据《Conventional Commits》规范，合并生成一个包含多项目变更明细的统一大 Commit 消息，对大仓库执行统一的 `git commit` 与 `git push`（同步到远程 CNB/GitHub 大库）。
    *   **第三步**：将新修改的文本块发送给 Embedding 模型，增量刷新本地向量库（ChromaDB）。
3.  **解除锁定**：后端三步执行完毕，返回成功信号，前端 Loading 消失，进度条扣满，大模型通过 MCP 实时吃到 100% 准确的最新向量索引。

### 模块 F：双重汇报与 WebSocket 轻量全量同步 (Dual Reporting & Debounced UI)
1.  **大模型终端汇报**：在引导 Prompt 中显式约束，大模型在 IDE 终端完成代码修改后，在对话框内主动向人类发送结构化的结项报告（包含代码修改明细与文档同步状态）。
2.  **WebSocket 轻量级通知**：后端落盘成功后，通过 WebSocket 向当前项目房间广播刷新事件。
3.  **前端防抖与弹窗降级**：
    *   **非当前项目**：如果 AI 修改的是项目 C，而用户正在看项目 A，大后台网页只在左侧侧边栏的项目 C 名字旁边默默亮起一个红点，绝对不弹出声音和打扰卡片。
    *   **当前项目**：只有当 AI 修改的项目正好是用户当前正在打开的项目时，前端大后台才在网页右上角弹出轻量级 Toast 提示。并且前端增加一个 500 毫秒的防抖阀门，拒绝复杂的流式打字机渲染，直接全量覆盖刷新当前 Markdown 组件视图，锁死浏览器 CPU 内存。
4.  **Markdown 与 Mermaid 延迟渲染**：前端右侧 Markdown 区域集成 `react-mermaid` 专用桥接组件锁死虚拟 DOM 节点。为了防止高频推流卡死网页，Mermaid 流程图必须在网页上设计成一个 **【点击加载/展开架构图】** 的折叠占位符，只有人类手动点击展开时，才去触发重型的 `mermaid.js` 渲染。
5.  **时光机对比器 (Version History Diff)**：引入 `react-diff-viewer` TypeScript 接口。点击“历史版本”时，后端直接执行 `git log` 和 `git show` 对大仓库执行指定路径分析。前端进入双栏对比视图：左栏加载历史 md 文本（并去 SQLite 捞出历史数据，复活已被擦除的飞书高亮气泡），右栏渲染当前干净主干，红绿双色高亮展示 AI 方案的进化轨迹。

---

## 🎨 4. 前端组件选型与第三方依赖全规格定义 (Frontend Tech Stack)

为了确保 React 18 + Vite 环境在打包、类型安全以及组件库交叉调用时绝对不崩溃，前端项目初始化必须锁定以下包管理规范。

### 1. 前端 `package.json` 依赖声明明细 (无精简)
```json
{
  "name": "evowiki-portal",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "antd": "^5.18.0",
    "@ant-design/icons": "^5.3.7",
    "tailwindcss": "^3.4.4",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0",
    "react-mermaid": "0.1.3",
    "mermaid": "^10.9.1",
    "react-diff-viewer-next": "0.1.0-alpha",
    "lucide-react": "^0.395.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.2.2",
    "vite": "^5.3.1"
  }
}
```

### 2. 五大核心交互组件详细技术选型与实现规范

#### 组件一：双层侧边栏导航树 (`EvoSideBarTree.tsx`)
*   **组件选型**：使用 Ant Design 的 `Layout.Sider` 嵌套 `Menu`（做第一层项目切换）和 `Tree`（做第二层文档树结构）。
*   **数据模型约束**：强行锁死 TypeScript 接口，防止 AI 自作聪明生成不合规的动态节点。
    ```typescript
    export interface EvoWikiTreeNode {
      title: string;
      key: string;       // 对应服务器磁盘上的相对物理路径 (如: 'project-alpha/docs/auth.md')
      isLeaf?: boolean;  // 是否是 Markdown 文件
      icon?: React.ReactNode; // 当节点属于 dependencies 挂载时，强制替换为 🔗 (LinkOutlined)
      children?: EvoWikiTreeNode[];
    }
    ```
*   **按需懒加载 (Lazy Load)**：文件树的大目录必须配置 `loadData` 异步钩子。点击文件夹时，仅向后端传递当前文件夹的 `key`，按需获取下一级 JSON，禁止一次性拉取万级企业文件流导致 DOM 卡死。

#### 组件二：飞书式划词拦截器 (`ContextualSelectionWrapper.tsx`)
*   **组件选型**：使用原生 JavaScript `window.getSelection()` API 拦截人类选区，配合 Ant Design 的 `Popover` 气泡定位。
*   **核心避坑架构**：**禁止使用 HTML 标签高亮，改用原生 Markdown 脚注映射。**
    *   人类在网页渲染出的文本中划选一段字，触发 `onMouseUp` 事件。
    *   计算出划词文本的内容 `selectedText`。点击气泡保存评论时，前端不改动任何 DOM 节点，而是向后端发送标准的映射指令。
    *   后端将此评论树持久化入 SQLite 评论表（字段：`id`, `project_id`, `file_path`, `anchor_text` [划词原文快照], `json_thread` [多轮评论盖楼数组]）。
    *   前端渲染时，通过 `react-markdown` 的自定义节点处理器（Components Override），发现文本中包含 SQLite 里记录的 `anchor_text` 时，动态套上自建的 `<span className="bg-yellow-100 border-b-2 border-yellow-400 cursor-pointer">` 样式，完美复活飞书视觉，同时保持底层 `.md` 文件的绝对纯净。

#### 组件三：侧边气泡盖楼卡片 (`CommentThreadPanel.tsx`)
*   **组件选型**：使用 Ant Design 的 `Card`、`List` 与 `Avatar` 拼装，常驻于 Markdown 渲染区域的右侧。
*   **数据驱动逻辑**：
    *   当人类点击网页上任何一个黄色高亮文本块时，激活该组件，传入当前划词评论的 `UUID`。
    *   组件从前端全局状态中读取并渲染对应的 `threads` 数组，以线性的时间线（Timeline 视觉）自上而下展示所有人类和 AI 的盖楼对话。
    *   卡片底部提供 **【Resolve (解决并擦除)】** 实体按钮。点击后调用后端的 `/api/comments/resolve` 接口，SQLite 中该评论状态置为已解决，前端通过全局状态无感干掉该高亮，主干文档无损。

#### 组件四：Markdown + 绝缘型 Mermaid 拓扑渲染器 (`EvoMarkdownViewer.tsx`)
*   **组件选型**：引入 `react-markdown` 主框架，挂载 `remark-gfm` 插件，图形渲染采用专属桥接组件 **`react-mermaid`**。
*   **虚拟 DOM 绝缘防死机逻辑**：
    *   为了防止大模型高频通过 WebSocket 全量推送文本时导致虚拟 DOM 频繁重绘，触发 Mermaid 引擎崩溃白屏，必须实施拦截：
    ```tsx
    import Markdown from 'react-markdown';
    import Mermaid from 'react-mermaid';

    const renderers = {
      code: ({ language, value }: { language: string; value: string }) => {
        if (language === 'mermaid') {
          // 封装为折叠占位符，默认不加载重型 SVG，只有人类手动点击开展时才激活渲染
          return (
            <details className="bg-gray-50 p-4 rounded border my-2">
              <summary className="cursor-pointer text-blue-600 font-semibold select-none">
                📊 点击展开/加载 AI 生成的架构时序图
              </summary>
              <div className="flex justify-center p-4">
                <Mermaid name={value} />
              </div>
            </details>
          );
        }
        return <pre><code>{value}</code></pre>;
      }
    };
    ```

#### 组件五：时光机 Git 历史版本对比面板 (`EvoTimeMachine.tsx`)
*   **组件选型**：引入 **`react-diff-viewer-next`** 开源 TypeScript 对比器。
*   **多版本重现流**：
    *   点击“历史版本”按钮，弹出半屏抽屉（Drawer），左侧是由后端的 `git log` 接口返回的线性时间轴。
    *   点击历史轴上的某一个 Commit（如：`v20260814-Codex重构`），前端向后端调用 `/api/history/show` 获取该版本的历史 md 源码。
    *   右侧主区域激活 `ReactDiffViewer`，左窗格展示历史旧文本，右窗格展示当前主干最新文本。系统自动配置 `oldValue` 与 `newValue`，以行业标准的高级红绿双色（删除线与新增线）完美复现资产演进历史。

---

## 🎛️ 5. 核心配置文件与接口定义 (Types Standard)

### 1. 项目元数据配置文件示例 (`meta.json`)
```json
{
  "project_name": "EvoWiki-Demo-Project",
  "description": "Evolight 团队的 AI 研发资产中枢示例",
  "dependencies": [
    "global-shared",
    "common-payment-spec"
  ]
}
```
