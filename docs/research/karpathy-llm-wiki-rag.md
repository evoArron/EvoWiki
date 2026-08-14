# Karpathy 的 LLM Wiki 与企业 Markdown RAG

- 研究日期：2026-08-14
- 目的：为企业 Markdown RAG 的产品设计讨论厘清概念，不构成实现建议或供应商背书。
- 结论置信度：高（核心概念直接来自 Karpathy 的公开 Gist）；中（企业收益与风险是基于该模式作出的工程推断）。

## 结论摘要

“Karpathy's LLM Wiki”目前可核验的源头是 Andrej Karpathy 于 2026-04-04 发布的公开 Gist `llm-wiki.md`，而非一个由他维护的产品、GitHub 仓库、MCP 服务或 RAG 框架。它提出的是一种**知识编译（knowledge compilation）模式**：不可变原始资料 -> LLM 持续维护的、互链的 Markdown wiki -> 约束 LLM 行为的 schema/instructions。与传统 RAG 的关键差异是，先在入库时把多源信息综合为可持久更新的 wiki，再主要从 wiki 进行问答；不是每次查询都仅从原始 chunk 临时拼接答案。

因此，答案是：**会在检索前用 LLM 生成/更新 Markdown，但不是编译器意义上的确定性“编译”，也不是取消检索。**原文建议查询先读 `index.md`，再读相关 wiki 页面；约约 100 个来源、数百个页面时可不使用 embedding RAG，规模增大后才可选本地全文/混合搜索工具。原始资料仍是不可变 source of truth；wiki 是有价值但可出错的派生层。

## 一手来源与归属

| 结论 | 证据 | 置信度 |
|---|---|---|
| Karpathy 本人发布了 `llm-wiki.md`，创建时间为 2026-04-04 16:25:13 UTC。 | GitHub Gist 页面；GitHub Gist commits API 显示首个 commit 的 `user.login=karpathy`、版本 `ac46de1...`。 | 高 |
| 该文明确称自己是 “idea file”，意在复制给 LLM agent，由用户与 agent 协作补全细节。 | Gist 的开头与末尾的 Note。 | 高 |
| 它不是 Karpathy 发布的可运行参考实现；目录、schema、页面格式、工具均“optional and modular”。 | Gist Note 明言是抽象模式，不是 specific implementation。 | 高 |
| 未找到 Karpathy 的官方仓库、论文或公开视频把该模式固化为另一套产品/算法。当前可核验的一手权威材料就是该 Gist；不能将后续博客或实现当作 Karpathy 的额外主张。 | 对 Karpathy GitHub Gists、GitHub 搜索结果和公开视频检索的限定性检查。 | 中（“未找到”不能证明不存在） |

主来源：

1. Andrej Karpathy, [llm-wiki.md Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)（一手、核心材料）。
2. GitHub API, [Gist commits](https://api.github.com/gists/442a6bf555914893e9891c11519de94f/commits?per_page=10)（一手平台元数据，用于作者与首次提交时间核验）。

## 原文模式：输入、处理、输出

### 三层与数据边界

```text
原始来源（raw，immutable）
  -> LLM 读取、抽取、综合、标注矛盾、更新链接
Wiki（LLM-owned Markdown：summary/entity/concept/comparison/overview/index/log）
  -> index-first 搜索与页面读取
回答/表格/报告等输出；有价值的回答可再写回 wiki

Schema（AGENTS.md / CLAUDE.md 等行为契约）约束 ingest、query、maintenance 工作流
```

**输入**：文章、论文、图片、数据文件等 curated sources；文中也举企业的 Slack 线程、会议转录、项目文档、客户通话为例。原文要求 raw sources 不被 LLM 修改。

**入库/编译（ingest）**：加入一个来源后，LLM 阅读来源，与人讨论重点，写 source summary，更新索引以及相关实体/概念页，记录日志；原文的示例称单一来源可能影响 10--15 个 wiki 页面。它要求持续处理新旧主张的矛盾和综合，不是单文摘要库。

**查询（query）**：LLM 先从内容索引 `index.md` 发现相关页面，再读取页面并给出带引用的综合答案。原文将索引方案定位于中等规模（约 100 个来源、数百页面）；更大时可选搜索工具，提到 `qmd` 的本地 BM25/vector 混合搜索与 LLM reranking。注意：这是建议的可选工具，不是 Karpathy 指定的企业技术栈。

**维护（lint）**：周期性找页面间矛盾、已被新资料替代的旧断言、孤儿页、缺失概念/链接、资料空白。`log.md` 为 append-only 的时间线；`index.md` 是按内容导航的目录，二者职责不同。

## 它与传统 Markdown RAG 的关系

| 维度 | 传统 RAG（典型） | LLM Wiki 模式 |
|---|---|---|
| 检索对象 | raw 文档 chunk | 优先是编译出的结构化 wiki 页面；深查时仍应回到 raw |
| 综合时机 | 查询时临时拼装 | 入库时持续综合，查询时复用并按需补充 |
| 可持久产物 | 向量索引/元数据，通常对人不友好 | 人可审阅、可版本控制、可互链的 Markdown wiki |
| 矛盾处理 | 可能到被问到时才暴露 | 目标是在入库/维护时标记并更新 |
| 是否完全取代 RAG | 不适用 | 否。Gist 明说大规模时可引入搜索；其差异主要是权威的派生知识层，不是反检索口号。 |

产品表述应避免写成“Not RAG”即“没有 retrieval”。更准确的是：**以编译后的 Markdown 作为优先检索层的、带原文可追溯回退路径的 RAG/知识库架构**。

## 预期收益

以下前三项是 Gist 的直接主张或自然直接后果；最后一项是企业工程推断。

1. **减少重复综合**：多文档的细微关系、交叉引用和已发现的矛盾不必在每次问答重新拼接。原文称知识会累计（compound）。置信度：高。
2. **可读、可审、可版本化的中间层**：Markdown + Git/Obsidian 使人可以实时浏览、diff、回滚、发现孤儿和知识图结构。置信度：高。
3. **降低维护摩擦**：LLM 可在一次入库中同时更新多个页面、链接和摘要；人类集中于资料选择、重点和判断。置信度：高（这是模式目标，不代表质量得到保证）。
4. **可把高价值问答沉淀为后续可检索资产**：减少聊天记录成为孤岛。置信度：高。
5. **企业中可将“原文证据”和“面向员工的当前结论”解耦**：后者适合快速问答，前者支持审计、重编译和争议复核。置信度：中（工程推断）。

## 失败模式与企业控制点

以下为工程推断，**不是 Karpathy 已验证的功能承诺**。其中第 1--4 是该模式相较仅保留 raw RAG 新增或加剧的主要风险。

| 风险/失败模式 | 为什么会发生 | 产品讨论的最低控制点 |
|---|---|---|
| 编译层幻觉或错误泛化 | LLM 在多个 raw source 间综合时可能遗漏限定条件、混淆实体或制造联系；错误会被多页复用。 | 每个断言/段落保留原始来源、位置与编译版本；高影响页面需人工审批或发布门禁。 |
| 语义漂移与陈旧结论 | 新源加入后只局部更新，overview、实体页和引用页可能不一致。 | 将 source 变更触发的影响面、待复核状态、过期时间显式化；lint 只发现问题，不能证明事实正确。 |
| 证据被摘要压缩丢失 | wiki 页面可读但不含原文所有细节；只搜 wiki 会漏掉长尾条款、例外和数字。 | 深度查询可回退 raw；在答案中显示“编译结论”与“原文证据”的区分。 |
| 写扩散和不可控变更 | 一次 ingest 可能改 10--15 页；错误或提示注入会扩大影响。 | raw 只读、派生 wiki 分支/PR/diff、最小写权限、变更审计、可重建派生层。 |
| 企业 ACL 泄漏 | 聚合页若混合不同权限来源，页面本身可能泄露原文不可见的事实。 | 在编译、索引、链接、查询四个阶段都按来源 ACL 过滤；不要仅在最终回答过滤。 |
| 时序/冲突失真 | “当前综合”容易覆盖曾经正确但已过期的内容，或把互相冲突来源强行统一。 | 保留来源时间、有效期、冲突状态和历史版本；把“未决冲突”作为一等状态。 |
| 成本与延迟前移 | 每次新增资料都要 LLM 读取和多页更新；批量导入可能昂贵且排队。 | 增量编译、按价值/风险分级、可中断重跑；不要承诺所有资料实时全量综合。 |
| 评估缺失 | “更少重复推理”不等于答案更正确。 | 以带权限的企业问题集分别评估 raw-only RAG、wiki-first、wiki+raw deep query 的准确性、引用完整性、时效和成本。 |

## 对 EvoWiki/企业 Markdown RAG 的可讨论定位

1. 可采用“**raw 不可变，wiki 可重建**”而非把 LLM 生成内容当唯一事实库。企业的 source of truth 应是受权限与版本管理的原始文档。
2. “编译”应是明确的异步/人工触发工作流，输出显示变更 diff、证据和冲突，不能把它伪装成无损转换。
3. 普通问答可先检索编译 wiki；涉及合规、合同、金额、时效、权限敏感信息时应自动或可选地验证 raw 证据。
4. 不要在第一版将它描述为替代向量检索。Markdown 索引/全文检索足以验证中等规模体验；在规模与召回问题确实出现后再加混合检索。

## 容易混淆的同名/近名项目

| 名称 | 可核验归属与性质 | 与 Karpathy 的关系 | 置信度 |
|---|---|---|---|
| [`karpathy/llm-wiki.md`](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | Andrej Karpathy 的概念 Gist。 | 原始概念来源。 | 高 |
| [`nvk/llm-wiki`](https://github.com/nvk/llm-wiki) / [llm-wiki.net](https://llm-wiki.net/) | GitHub 仓库元数据的 owner 是 `nvk`；MIT 实现，README 自称支持 Claude/Codex/OpenCode/Pi，含 ingest/compile/query/lint 等工作流。README Credits 将 Karpathy 列为“LLM wiki concept”。 | 受该概念启发的独立实现，不是 Karpathy 的仓库或官方实现。 | 高 |
| [llm-wiki.app](https://llm-wiki.app/) | 公开落地页宣称 “Wiki-first knowledge” 和 “Not RAG. Not Search. Compilation.”，页面上未见 Karpathy 为作者/运营方的可核验证据。 | 名称与叙事相近；不得归因给 Karpathy，也不能拿它的承诺作为原概念能力证据。 | 中 |
| 各类 “Karpathy-style/ Karpathy's LLM Wiki” 模板、博客和复刻仓库 | 搜索结果中的二手解释或社区实现。 | 仅是诠释/复刻，除非其作者与来源另有可验证关系。 | 高 |

`nvk/llm-wiki` 的可复核资料：GitHub [repository metadata](https://api.github.com/repos/nvk/llm-wiki)（owner=`nvk`）与其 [README at commit `75e82a5`](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/README.md)（Credits 和实现声明）。它对 Karpathy Gist 的解读有参考价值，但不是一手证据。

## 讨论时应追问的问题

1. 哪些知识域允许“当前综合结论”作为首选答案，哪些必须逐条回链原文？
2. 一个 wiki 段落的最小可审计单元是什么：页级 sources、段落级 citation，还是 claim-level provenance？
3. 当更新一个源文件时，如何精确找出需要重编译的 wiki 页面，而不盲目全量刷新？
4. ACL 改变、文档撤回、法务保留期到期时，raw、索引、派生 wiki、缓存和历史版本如何同时处理？
5. 成功指标是问答 token/延迟下降、跨文档问题正确率提升、人工维护时间下降，还是三者都要？没有基准集就无法证明“编译”优于现有 RAG。

## `nvk/llm-wiki` 实现核验与 EvoWiki V1 取舍（2026-08-14）

### 核验范围与证据等级

本节固定核验 [`nvk/llm-wiki` commit `75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0`](https://github.com/nvk/llm-wiki/tree/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0)（`master` 于 2026-08-12 的 HEAD）。下述“已验证”均来自该 commit 的源码或测试，不以 README 宣传替代实现。与原始概念的比较固定到 Karpathy 的 [Gist revision `ac46de1`](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f/ac46de1ad27f92b28ac95459c782c07f6b8c964a)。

**实现边界，已验证：**它不是一个提供向量库、embedding、ACL 或在线 RAG API 的服务。其主体是给 Claude/Codex/Pi 等 agent 的 Markdown 协议、命令提示和 fixtures；本地 Python 工具实际实现的子命令仅为 `lint`、`archive`、`schema`、`retract`，[见 `scripts/llm-wiki`](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/scripts/llm-wiki)。`ingest`、`compile`、`query`、`refresh` 主要是 agent 应遵守的工作流文本，而非可独立执行的编译器或查询后端。[测试说明](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/tests/README.md)也证实其确定性测试覆盖文件结构、frontmatter、链接和索引；行为评估才调用模型。

### 与 Karpathy Gist 的比较

| 维度 | Karpathy 原始 Gist | `nvk/llm-wiki` 固定提交的已验证做法 | 对 EvoWiki 的含义 |
|---|---|---|---|
| 定位 | 抽象且模块化的“idea file”；目录、格式与工具由使用者决定。 | 将概念具体化为 topic hub、`raw/`、`wiki/`、`output/`、`_index.md`、frontmatter、命令和 lint 规则。 | 可以借鉴其文件边界，不能把其协议误认为企业级运行时。 |
| 生成什么 | source summary、实体/概念/比较/overview/index/log；一份新源可影响 10--15 页。 | 增量 compile 从 raw 生成 `concept`、`topic`、`reference` 三类合成文章，带摘要、`sources:`、confidence、volatility、双向交叉链接和索引；生成的交付物另放 `output/`。见[编译协议](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/compilation.md)。 | V1 只需要“带来源的派生 Markdown 页面 + 发布索引”，不需要 Ideas、Portfolio、session memory、Obsidian 双链接等外围模型。 |
| 原文与编译层 | raw 是不可变 source of truth，LLM 维护 wiki。 | `raw/{articles,papers,repos,notes,data}` 是不可变来源，`wiki/{concepts,topics,references}` 是综合层，`output/` 是生成交付物；大型/外部数据只登记 `datasets/<slug>/MANIFEST.md`，不复制进 Markdown。见[结构与原则](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/AGENTS.md)与[数据集协议](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/datasets.md)。 | 该分层适合 EvoWiki，但 raw 的物理文件、SQLite 元数据、Git 提交和向量索引必须同属一个版本发布单元。 |
| 查询 | `index.md` 先导航，再读页；约 100 个源/数百页可不使用 embedding，规模更大时才可选搜索。 | read-only query 先读 root/branch indexes，再最少量读候选文章；`wiki/` 是默认事实层，用户要求原始证据或编译覆盖不足时再读 `raw/`。索引是可由 Markdown/frontmatter 重建的缓存，而非 truth。见[Query Lite](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/query-lite.md)和[索引协议](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/indexing.md)。 | 保留 wiki-first，但不要把 raw fallback 降格为“用户明确请求才可用”。EvoWiki 应在无可发布 wiki 命中、证据不足、时效/高风险问题时自动回退 ACL 过滤后的 raw RAG。 |

### (1) 实现实际建议生成的内容

**已验证仓库实践：**compile 的输入是完整读取的未编译 raw source；输出不是逐源摘要库，而是合成的概念、主题和参考页。每个原始来源可新增或更新已有页；文章须列出 raw `sources:`，添加 `## Sources` 和双向 `See Also`，并在 frontmatter 标明 `confidence`、`volatility`、`verified`。编译后更新分类索引、总索引和 append-only `log.md`。[`compile.md`](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/commands/compile.md)还要求在写后重新读取并验证每个受影响文章的来源、volatility、verified、confidence。

**EvoWiki 建议：**V1 生成最小的三类派生物：`wiki/` 中的综合 Markdown、每篇的结构化 source 引用、该发布版本的导航索引。不要在 V1 生成活动日志摘要、研究 session、库存/项目/Idea 对象或大量“自动补全”文章。回答产物可另存，但不应自动成为可检索事实。

### (2) raw source 与 compiled wiki 的分离

**已验证仓库实践：**单源 ingest 将外部内容标准化写入 `raw/`；collection ingest 额外写一个 `raw/repos/` manifest 和逐上游项的 immutable child source。child frontmatter 可含 `collection`、`upstream_id`、`revision`、blob/content `sha`、canonical URL、作者、抓取日等；相同 `collection + upstream_id + revision/sha` 去重，上游变更时应新写 raw source，不能覆盖旧文件。[采集协议](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/ingestion.md)。这比 Karpathy Gist 的“raw immutable + wiki LLM-owned”提供了可执行的目录和 provenance 字段。

**需注意的实现矛盾：**上述 collection 规则与 [refresh 命令](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/commands/refresh.md)的 `update` 步骤不一致，后者明确写“overwrite the raw file”。前者保留历史，后者破坏 immutable raw。因此不能把 refresh 的覆盖语义作为 EvoWiki 实践采纳。

**EvoWiki 建议：**V1 中 raw 必须是不可改的版本对象：`source_id + content_hash + source_revision + fetched_at + ACL snapshot`，原始/转换后的正文置于受控文件路径，元数据和版本关系置于 SQLite。编译结果只指向具体 raw version；发布时把 raw 版本、compiled Markdown、SQLite 版本记录和 ChromaDB 索引一起绑定到同一 Git commit。更新源文件应新增 version，再创建新的“待发布编译版本”，绝不就地覆盖既有 raw 或已发布 wiki。

### (3) provenance、引用与更新

**已验证仓库实践：**

- wiki article 的 `sources:` 必须解析到 raw 文件；lint 同时检查悬空来源、未解决撤回标记、未被引用的 raw source、文章缺失来源，并为未编译 source 建显式 coverage backlog。[lint 规则 C4b/C6/C18](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/linting.md)。本地 CLI 与其测试实际执行并覆盖其中一部分结构性检查。[CLI 测试](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/tests/test-local-cli-lint.sh)。
- query 必须给精确文件路径 citation，区分 synthesis、raw evidence 和 inventory；默认不写，且不以模型记忆填补证据空缺。[Query Lite](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/query-lite.md)。
- maintenance 以 `verified`、`updated`、source age、source-chain integrity 和 `hot/warm/cold` 算 freshness；librarian 先打分、再由人确认处理，不在扫描时改正文。[librarian 协议](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/librarian.md)。
- index 是从文件/frontmatter 重建的缓存，write 后更新可 best-effort。这适合个人多 agent 文件夹协作，但不是强一致发布机制。

**EvoWiki 建议：**V1 的最小引用粒度应为“编译段落/claim -> raw source version -> 原文定位（页码、heading、字符范围或 chunk id）”，答案输出必须带可访问性已过滤的 citation。更新后要计算受影响 compiled 页并标记 `draft/stale`，由显式发布操作生成新的 Git commit；仅在同一发布版本内检索 wiki 与 raw index。ACL 改变、撤回和源删除必须使对应 wiki、索引和 citation 立刻不可见，而不只是最终答案过滤。

### (4) 长文件指导的实际范围

**已验证仓库实践：**它有几项局部的长内容处理规则，但没有通用的“长 Markdown 分块、层级摘要、重组再编译”算法：

- 大型、可变、远程、二进制或更适合原生查询的数据不写入 Markdown，而是外置并用 dataset manifest、少量 sample 和 query recipe 索引；sample 默认最多 20 行。[dataset 协议](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/datasets.md)。
- 大型 MediaWiki dump 要 streaming XML，不可整个载入内存；大 collection 先 dry-run、估算 child 数量，再选择 dataset 或 collection ingest。[ingestion](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/references/ingestion.md)。
- agent 的单次 Write 被限制在约 200 行，要求 skeleton 后用 Edit 分段追加，这是防工具流超时的写入指导，不是源文档 token 上限策略。[wiki-manager SKILL](https://github.com/nvk/llm-wiki/blob/75e82a56c74ee8df24e5d4b7bb772b5b648e0ec0/claude-plugin/skills/wiki-manager/SKILL.md)。
- 反面证据是 compile 仍要求“Read each uncompiled source in full”；因此对超长 PDF/Markdown 的可靠抽取、分段证据引用与跨段综合并未被该实现解决。

**EvoWiki 建议：**V1 对 raw RAG 建立稳定、可复现的 heading/page-aware chunks，并把 `raw_version_id`、范围和 hash 写入 SQLite；compile 只读取任务相关的 chunk 集与其相邻上下文。长文件先产生可审查的 source outline 和段级引用，再产出 wiki 页。V2 才考虑多层摘要和自动影响图；不要用一次性把完整长文件塞进模型的协议替代 chunk retrieval。

### (5) EvoWiki 分期决策

| 决策 | 内容 | 原因 |
|---|---|---|
| **V1 采用** | raw/compiled/output 物理隔离；raw 不可变；每个 compiled 页有可解析来源；index-first wiki 检索；结构 lint；Git commit/diff；发布版本绑定；ACL 过滤后的 raw-RAG fallback。 | 继承该仓库和 Gist 的核心价值，同时满足 EvoWiki 的 SQLite、Git、版本发布和严格 ACL 边界。 |
| **V1 采用，但收紧** | 增量编译、confidence/verified/staleness 字段、lint 发现 orphan/dangling source。 | 不允许 agent 直接写已发布页，也不允许“best-effort index 重建”跨越发布边界；必须先生成 draft，审批/同步后原子发布。 |
| **V2** | collection manifest 的 upstream revision/hash；依赖影响分析与 selective recompile；人工确认的 freshness/refresh；大数据 manifest；质量评分和 audit 报告。 | 这些有效但依赖 source version、发布状态和 ACL 传播已先建立。 |
| **拒绝** | refresh 覆盖 raw；查询仅在用户主动要求时才读 raw；跨 topic 自动读取正文；把 `_index.md` 当作唯一可重建但无版本门禁的缓存；自动 session/feedback 晋升为知识；将该仓库称为已实现 ACL/RAG 后端。 | 前三者分别破坏版本证据链、raw-RAG 召回和最小权限；其余会绕过 EvoWiki 的版本化发布、数据隔离或事实边界。 |

### 可执行结论

对 EvoWiki V1，采用的是“**versioned, ACL-filtered wiki-first RAG with raw fallback**”，不是复制 `nvk/llm-wiki` 的完整个人 agent 体系。Karpathy 提供了派生 wiki 的概念；`nvk/llm-wiki` 提供了可借鉴的 Markdown 结构、provenance frontmatter、lint 和索引工作流；ACL、发布事务、raw 版本不可变性与检索回退仍必须由 EvoWiki 自己实现和验证。
