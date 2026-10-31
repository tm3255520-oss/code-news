# Obsidian Wiki 知识沉淀架构研究简报

生成时间：2026-08-01

研究目标：为重构当前 Obsidian Vault 的 `wiki/` 知识沉淀层寻找外部高质量参考，先补足资料和工具样本，再决定最终方案。

## 资料归档

已下载到：

- `research/obsidian-wiki-architecture/articles/`
- `research/obsidian-wiki-architecture/tools/`

文章与工具资料均保留来源 URL 和抓取时间。

## 一、成熟做法的共同结论

### 1. 知识库不是 RAG，而是编译后的长期资产

Karpathy LLM Wiki / ClawHub LLM Wiki 系列反复强调一个原则：RAG 是每次查询时从原始文档重新推导答案；Wiki 是把知识编译一次，并持续维护。它要求 raw/source 层不可变，wiki 层持续更新，交叉引用、矛盾、索引和日志都被长期维护。

可借鉴点：

- `raw/` 或 `sources/` 是事实来源，尽量不可变。
- `wiki/` 是被整理、合并、更新后的知识层。
- 每次 ingest 不应只生成孤立摘要，而应更新已有页面。
- 查询时优先读已编译的 wiki，再回到 raw 查证。
- 有价值的问答也应该沉淀回 wiki。

对应资料：

- `tools/clawhub-karpathy-llm-wiki.md`
- `tools/clawhub-lhuaizhong-llm-wiki.md`
- `tools/clawhub-obsidian-llm-wiki.md`

### 2. Zettelkasten / Evergreen 的关键不是分类，而是长期演化

Andy Matuschak 的 Evergreen Notes、Yordi 的 Zettelkasten + Obsidian 工作流、Obsidian Forum 的实践都指向同一个核心：真正有价值的是 permanent / evergreen notes，而不是原始摘要。

成熟链路通常是：

```text
Inbox / Fleeting
  -> Source / Literature Notes
  -> Permanent / Evergreen Notes
  -> MOC / Hub
  -> Writing / Output
```

可借鉴点：

- permanent note 不是来源摘要的拆分，而是用自己的话写成的独立思想。
- 每张知识卡最好只承载一个可复用观点。
- Evergreen page 应该持续演化、概念导向、链接密集。
- MOC/Hub 是导航和综合层，不是单纯文件夹。

对应资料：

- `articles/andy-matuschak-evergreen-notes.md`
- `articles/yordi-zettelkasten-obsidian.md`
- `articles/obsidian-forum-zettelkasten-practices.md`
- `articles/obsidian-rocks-moc.md`

### 3. MOC / Hub 是你当前 wiki 缺失的关键层

Obsidian Rocks 和 LYT/MOC 相关资料的共同观点是：文件夹太硬，标签太松，MOC 用来人工/半自动地组织“主题入口”。MOC 不必保存大量正文，但要回答：

- 这个主题下有哪些核心问题？
- 哪些概念、实体、来源和输出属于这个主题？
- 当前有哪些空白、争议、可写选题？

对你的 Vault 来说，`wiki/concepts/` 和 `wiki/summaries/` 已经有不少文件，但缺少把它们组织成主题地图的 `mocs/` 或 `topics/` 层。

### 4. 工具只能解决访问、检索和维护动作，不能自动保证知识质量

Obsidian MCP / Research MCP / Smart Connections / qmd 等工具主要解决：

- 让 Agent 读取、写入、移动 Obsidian 文件。
- 维护 wikilink、backlink、Dataview、Bases。
- 进行语义检索、关系分析、孤立页检测。
- 降低搜索和读取成本。

它们不能替代知识 schema。没有明确页面类型、质量门槛和 ingest/lint 流程，工具只会更快地产生更多占位符。

## 二、最接近的 Skill / MCP 候选

### A. ClawHub / OpenClaw 方向

#### 1. `karpathy-llm-wiki`

来源：`https://clawhub.ai/john-ver/skills/karpathy-llm-wiki`

定位：最接近“AI 维护长期 Markdown Wiki”的方法论 Skill。

核心设计：

- 三层：`sources/`、`wiki/`、schema。
- `sources/` 不可变，`wiki/` 由 Agent 维护。
- 页面类型：entity、concept、summary。
- 每页必须有 summary、key facts/claims、related、counter-arguments/data gaps、sources。
- 每次 query 先读 `index.md`。
- lint 检查 contradictions、stale claims、orphan pages、missing pages、missing cross-references、index gaps。

可借鉴程度：高。

不建议照搬点：

- 它默认 wiki 结构较扁平，你的 Vault 已经有 raw/wiki/outputs/workflows 等业务层，不必完全替换。
- 它的 summary page 概念偏宽，需和你的 `summaries/`、`sources/` 区分清楚。

#### 2. `lhuaizhong-llm-wiki`

来源：`https://clawhub.ai/lhuaizhong/lhuaizhong-llm-wiki`

定位：更通用的 local-first Markdown wiki 维护 Skill。

核心设计：

- 推荐结构：`raw/`、`wiki/`、`logs/knowledge-log.md`、`INDEX.md`、`SCHEMA.md`。
- 操作模式：ingest、query、reindex、lint。
- 强调“更新已有页面优先于创建近似重复页面”。
- 对 Obsidian 的建议是：普通 Markdown、保留 wikilinks、稳定文件名、密集主题用 hub page。

可借鉴程度：高。

不建议照搬点：

- 它偏通用，缺少你做内容生产时需要的平台输出、素材类型、选题池等业务字段。

#### 3. `obsidian-llm-wiki`

来源：`https://clawhub.ai/eddiewang-zhhx/obsidian-llm-wiki`

定位：中文 Obsidian + LLM Wiki Skill，和你的使用场景最接近。

核心设计：

- raw 不可变，wiki 由 AI 维护。
- wiki 下分 `sources/`、`entities/`、`topics/`、`comparisons/`、`synthesis/`。
- 使用 Obsidian CLI 做 lint、search、backlinks、links、orphans、deadends。
- 记录了一个重要工程经验：Obsidian CLI 的 `content` 参数不适合长内容，长内容应直接写文件，短日志可用 CLI append。

可借鉴程度：高。

不建议照搬点：

- 该 Skill 声称“AI 完成所有整理工作”，实际落地时仍必须保留人工确认质量门槛。
- 目录里的 `entities` 同时包含人物、产品、概念、工具，边界略松；你的 Vault 应继续区分 concepts / entities。

#### 4. OpenClaw `wiki` CLI

来源：`https://docs.openclaw.ai/cli/wiki`

定位：更系统化的 wiki 命令层。

可借鉴点：

- `wiki status` / `doctor` / `init` / `ingest` / `lint` / `search` / `get`
- `wiki apply synthesis`、`apply metadata`
- `source-evidence`、`raw-claim` 等检索模式，强调证据和 claim metadata。
- `lint` 在信任知识库前执行。

可借鉴程度：中高。

不建议照搬点：

- 如果你当前 Hermes 环境未集成 OpenClaw wiki CLI，不应为了架构重构引入整套运行时。
- 可先借鉴命令语义，后续再决定是否落工具。

### B. GitHub MCP / Obsidian 工具方向

#### 5. `entanglr/zettelkasten-mcp`

来源：`https://github.com/entanglr/zettelkasten-mcp`

定位：Zettelkasten 方法论 MCP。

核心设计：

- note types：fleeting、literature、permanent、structure、hub。
- link types：reference、extends、refines、contradicts、questions、supports、related。
- Markdown 是 source of truth，SQLite 是索引层，可重建。
- 提供 orphan、central notes、similar notes、linked notes 等工具。

可借鉴程度：高，尤其是 note type 和 link type。

不建议照搬点：

- 它是独立 Zettelkasten 系统，不是现成适配你当前 Obsidian 目录的方案。
- timestamp ID 和 SQLite 索引可后置，不是第一阶段刚需。

#### 6. `aaronsb/obsidian-mcp-plugin`

来源：`https://github.com/aaronsb/obsidian-mcp-plugin`

定位：成熟的 Obsidian MCP 访问层。

核心能力：

- 插件运行在 Obsidian 内部，MCP 通过 HTTP 暴露。
- 支持 vault 操作、edit、view、graph、workflow、dataview、bases、system。
- 支持权限控制、read-only、路径 allow/block。
- 支持图谱遍历、backlink/forward link、Dataview 和 Bases。

可借鉴程度：中高。

适合用途：

- 后续如果要让 Agent 稳定操作 Vault，这是很好的接入层候选。

不解决的问题：

- 它不定义你的 wiki 知识 schema。
- 它能让 AI “操作更强”，但不会让 AI “沉淀更好”。

#### 7. `wienkers/obsidian-research-mcp`

来源：`https://github.com/wienkers/obsidian-research-mcp`

定位：研究型 Obsidian MCP。

核心能力：

- Smart Connections 语义搜索。
- Pattern search / regex / context windows。
- 精准写入，保留 frontmatter。
- relationship analysis：backlinks、forward links、tags、mentions、embeds。
- content analysis：标题、列表、代码块、任务、表格。
- 使用场景包含 knowledge gaps 和 missing connections。

可借鉴程度：中高。

适合用途：

- 后续做 wiki 巡检、空白页识别、关系分析、缺口发现。

不解决的问题：

- 仍是工具层，不是知识方法论层。

#### 8. `qmd`

来源：`https://clawskills.sh/skills/anshumanbh-anshumanbh-qmd`

定位：Markdown 知识库搜索 Skill。

核心能力：

- BM25 / vector / hybrid search。
- 返回片段而不是全文，降低 token。
- 适合大 Vault 检索。

可借鉴程度：中。

风险：

- clawskills 页面显示 VirusTotal Suspicious，不能直接安装到生产环境。
- 可以先借鉴“片段检索 + 路径 + 上下文”的思路，暂不安装。

#### 9. Smart Connections

来源：`https://github.com/brianpetro/obsidian-smart-connections`

定位：Obsidian 语义关联插件。

可借鉴点：

- 自动索引 Vault。
- 提示语义相关笔记。
- 适合辅助发现隐藏关联。

限制：

- 它提示“可能相关”，不负责判断是否应该合并、链接、沉淀。

#### 10. `graphthulhu`

来源：`https://clawskills.sh/skills/skridlevsky-graphthulhu`

定位：Logseq / Obsidian 知识图谱读写 MCP。

可借鉴点：

- 覆盖导航、搜索、写作、分析、决策、journal、flashcard、whiteboard 等 37 工具。

限制：

- 范围太大，作为第一阶段可能过重。

## 三、对当前 Vault 的直接启发

你的当前结构：

```text
raw/
wiki/concepts/
wiki/entities/
wiki/summaries/
wiki/outputs/
wiki/postmortems/
wiki/workflows/
工作汇总/
内容生产/
```

最大问题不是目录不够，而是 `wiki/concepts/` 和 `wiki/summaries/` 没有形成“编译知识层”。

结合外部资料，建议后续方案必须满足：

### 1. 明确分层

建议把 `wiki/` 内部概念重新定义为：

```text
wiki/sources/ 或 wiki/summaries/
  来源笔记：每篇材料的证据、claim、可沉淀点

wiki/concepts/
  常青知识卡：一个可复用概念/判断/机制

wiki/entities/
  实体页：工具、公司、人物、项目、协议

wiki/topics/ 或 wiki/mocs/
  主题地图：组织 concepts/entities/sources/outputs

wiki/synthesis/
  综合报告：跨来源、跨主题的阶段性判断

wiki/outputs/
  平台成品，不承担知识源职责
```

### 2. 增加质量门槛

`concepts/` 不应允许空白占位符进入稳定状态。

建议状态：

- `seed`：种子概念，只能是占位，不能作为输出依据。
- `source-backed`：有来源和基本定义。
- `evergreen`：有边界、机制、例子、关系和复用观点。
- `stale`：可能过期。
- `conflicted`：存在来源冲突。

### 3. 每次 ingest 的成功标准要改

不再以“生成了几个 md 文件”为成功，而是：

- 是否更新了已有 concept/entity/topic？
- 是否新增或强化了至少 1 个可复用观点？
- 是否挂入某个 MOC/topic？
- 是否保留来源证据？
- 是否标记了不确定或冲突？

### 4. Lint 必须成为正式流程

借鉴 Karpathy LLM Wiki、OpenClaw wiki 和 Obsidian CLI：

- 空白页 / seed 页过多。
- orphan pages。
- deadend pages。
- missing cross-references。
- duplicate concepts。
- stale claims。
- contradictions。
- index gaps。

当前 Vault 最应该先 lint 的是：

- `wiki/concepts/`：大量 300 字节左右的 seed 页。
- `wiki/summaries/`：大量 600-1000 字节的轻摘要。
- `wiki/outputs/`：检查输出是否能追溯到 source/concept/topic。

### 5. 工具落地顺序

不要第一步就装一堆插件或 MCP。建议顺序：

1. 先定 `SCHEMA.md` 和 `INDEX.md` 规则。
2. 用本地脚本做静态 lint：空白页、孤立页、断链、重复标题、缺来源。
3. 再考虑 Obsidian CLI / Obsidian MCP Plugin 作为操作层。
4. 最后考虑语义搜索：Smart Connections、qmd 类能力。

## 四、候选借鉴优先级

### 第一优先级：方法论直接采用

1. `karpathy-llm-wiki`
2. `lhuaizhong-llm-wiki`
3. Andy Evergreen Notes
4. Zettelkasten note types：fleeting / literature / permanent / structure / hub

### 第二优先级：工具能力借鉴

1. Obsidian CLI lint/search/backlinks/orphans/deadends
2. `aaronsb/obsidian-mcp-plugin`
3. `wienkers/obsidian-research-mcp`
4. Smart Connections

### 第三优先级：后续可评估

1. `entanglr/zettelkasten-mcp`：适合独立知识图谱或二期增强。
2. OpenClaw `wiki` CLI：适合未来如果要统一到 OpenClaw runtime。
3. `qmd`：思路有用，但安全标记需要谨慎。
4. `graphthulhu`：能力太广，暂不作为第一阶段核心。

## 五、下一步建议

下一步不要直接重构所有文件。建议先做一个“设计前验证”：

1. 选 3 个主题：
   - Agent 工作流
   - Skill 系统
   - AI 内容生产系统
2. 为每个主题建一张 MOC/topic 页面。
3. 从现有 `summaries/`、`concepts/`、`entities/` 中只挑最相关的挂进去。
4. 对每个主题生成一份 synthesis。
5. 用 lint 检查：
   - 有多少 seed 概念没有来源？
   - 哪些 concept 重复？
   - 哪些 summary 没有流入任何 topic？
   - 哪些 output 没有上游来源链？

只有这一步跑通，才值得批量改造整个 wiki。

