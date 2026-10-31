# 上游出处与引入范围

## 来源

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/feicaiclub/video-spec-builder |
| 协议 | MIT（见同目录 `LICENSE`） |
| 引入版本 | commit `9e73275b35e827b8f7af4bca900790909d86e63e` |
| 上游提交日期 | 2026-05-18 |
| 引入日期 | 2026-09-16 |
| 上游星标 | 974 |

## 为什么引入

按项目「先 find-skills 找最接近的 → 再借鉴开发」的决策流程：
四平台检索后，该仓库的**分镜拆解方法论**与**节奏量化规范**是最成熟、且原生对接
HyperFrames 渲染栈的一份。整包安装会带进不适配的部分（见下），故只引入需要的三份。

## 引入了什么

| 文件 | 上游路径 | 处理 |
|---|---|---|
| `references/scene-breakdown.md` | 同名 | **逐字未改** |
| `references/pacing-rules.md` | 同名 | **逐字未改** |
| `references/spec-rules.md` | 同名 | **逐字未改** |
| `upstream/LICENSE` | `LICENSE` | 逐字未改 |
| `upstream/README.zh.md` | `README.zh.md` | 逐字未改（供追溯上游定位） |

保留原文而**不重写**，是为了可追溯与可升级：上游更新时可直接 diff。

## 刻意没有引入（以及为什么）

| 上游文件 | 体量 | 未引入原因 |
|---|---|---|
| `references/question-bank.md` | 61 KB | 面向**苏格拉底式逐轮访谈**；本产线是批处理，不做交互追问 |
| `references/components-catalog.md` | 39 KB | 上游 8 套预设主题的**组件 ID 库**；本产线使用自有卡片模板，引入会诱导 agent 引用不存在的组件 |
| `references/dialogue-style.md` | 7.2 KB | 追问语态规范，交互模式专用 |
| `templates/video-spec-template.md` | 5.5 KB | 9 节 markdown 交付格式；本产线产物是 JSON，喂渲染器 |

**未引入的部分不是"质量差"，而是"形态不匹配"。** 引入它们会同时背上两套视觉系统与两种交互模式。

## 必读：替换规则

上游原文中出现的以下概念，在本产线**一律替换**（详见 `references/适配说明.md`）：

- 「组件 ID」→ 我们的卡片内容块类型（`blocks[].label` 的自由文本）
- 「视觉主题 / HyperFrames 8 预设」→ 我们的卡片模板（`video-line/card-deck`）
- 「预估时长」→ **TTS 实测时长**（配音先行，ffprobe 回填）
- 「9 节 markdown 交付件」→ `storyboard.json`

原文里出现的 `components-catalog.md` 引用在本技能内**不成立**，按上文替换。

## 升级方式

```powershell
# 对比上游是否更新，需要时重新同步这三份
curl.exe -s "https://api.github.com/repos/feicaiclub/video-spec-builder/commits/HEAD" |
  Select-String '"sha"'
```
