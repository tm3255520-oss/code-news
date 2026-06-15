# 三平台内容发布总控链路设计

日期：2026-06-09  
范围：今日头条、知乎、公众号  
不包含：小红书正式发布链路

## 1. 背景

当前仓库已经具备三类能力：

1. 内容与素材生成
2. 单平台浏览器自动发布
3. 质量与发布准备度检查

但这三类能力还没有被收束成一条“可阻断、可追踪、可复核”的生产链路。结果是：

- 低质量稿件可能直接进入发布阶段
- 平台脚本各自记录状态，口径不统一
- 同一内容在状态不明时存在重复发布风险
- “已提交”“待验证”“已发布”容易被混用
- 用户无法从一个状态文件直接判断这篇内容还能不能继续发

本设计采用“统一总控层 + 保留现有平台脚本”的方式，建立三平台正式链路，而不是重写整个系统。

## 2. 目标

目标只有四个：

1. 把现有生成、配图、发布脚本接成一条正式三平台链路
2. 在发布前加入硬门禁，拦截低质量、缺素材、重复内容
3. 为每篇文章建立唯一状态文件，统一记录三平台发布状态
4. 在任何状态不明确时，先验证旧状态，不允许直接重发

## 3. 非目标

本轮不做以下事情：

1. 不重写现有三套浏览器发布脚本
2. 不接入小红书正式发布
3. 不做 PPT、海报、卡片二次分发
4. 不追求一次性解决所有内容选题问题，只先把“弱稿不进线”做成制度

## 4. 当前系统结论

现有主要文件：

- `scripts/check_generated_article_quality.py`
- `scripts/check_publish_readiness.py`
- `scripts/run_daily_content_ops.py`
- `.tmp/publish_toutiao_article.js`
- `.tmp/publish_zhihu_article_controlled.js`
- `.tmp/publish_wechat_article_controlled.js`
- `.tmp/render_toutiao_assets.js`

现状判断：

1. 质量脚本已经存在，但只输出报告，不阻断发布
2. 三个平台各自保存记录，但没有统一 source of truth
3. 今日头条已实现较强的本地去重，但最终状态仍依赖后验列表验证
4. 公众号重复发布的根因不是“没做去重”，而是“状态模糊时又重新提交”
5. 当前最需要补的是统一状态机，不是再做一套新生成器

## 5. 总体方案

方案采用一层新的总控 orchestrator，外层统一做：

1. 载入 payload 与素材
2. 运行质量门禁
3. 检查素材完整性
4. 计算内容指纹
5. 载入并更新统一状态文件
6. 先做重复与历史状态校验
7. 按平台顺序执行发布
8. 对每个平台写回统一状态
9. 生成最终结果摘要

现有平台脚本保留，只做两类增强：

1. 接受统一状态文件输入
2. 在状态不明时先做验证，不允许直接二次提交

## 6. 核心数据结构

每篇文章以现有生成目录为主目录：

- `.tmp/generated/<slug>/`

在该目录下新增：

- `.tmp/generated/<slug>/pipeline-state.json`

该文件是唯一事实来源，字段建议如下：

```json
{
  "schemaVersion": 1,
  "slug": "2026-06-09-example",
  "fingerprint": "sha256...",
  "title": "文章标题",
  "createdAt": "2026-06-09T12:00:00+08:00",
  "updatedAt": "2026-06-09T12:10:00+08:00",
  "qualityGate": {
    "status": "passed",
    "score": 84,
    "failCount": 0,
    "warnCount": 2,
    "checkedAt": "2026-06-09T12:02:00+08:00",
    "reportMarkdownPath": ".tmp/quality-gates/...",
    "reportJsonPath": ".tmp/quality-gates/..."
  },
  "assets": {
    "coverExists": true,
    "bodyImageCount": 3,
    "missingFiles": []
  },
  "platforms": {
    "toutiao": {
      "status": "published_verified",
      "attemptCount": 1,
      "lastAttemptAt": "2026-06-09T12:05:00+08:00",
      "publishedAt": "2026-06-09T12:08:00+08:00",
      "url": "https://...",
      "titleUsed": "平台标题",
      "verificationSource": "article_list_check",
      "error": null
    },
    "zhihu": {
      "status": "ready",
      "attemptCount": 0,
      "lastAttemptAt": null,
      "publishedAt": null,
      "url": null,
      "titleUsed": null,
      "verificationSource": null,
      "error": null
    },
    "wechat": {
      "status": "awaiting_verification",
      "attemptCount": 1,
      "lastAttemptAt": "2026-06-09T12:06:00+08:00",
      "publishedAt": null,
      "url": null,
      "titleUsed": "平台标题",
      "verificationSource": "editor_submit",
      "error": null
    }
  }
}
```

## 7. 状态机

统一状态只允许以下值：

- `draft_ready`
- `quality_failed`
- `asset_failed`
- `duplicate_blocked`
- `ready`
- `publishing`
- `submitted`
- `awaiting_verification`
- `published_verified`
- `publish_failed`

状态规则：

1. `quality_failed`、`asset_failed`、`duplicate_blocked` 一律禁止进入平台发布
2. `published_verified` 一律禁止再次提交
3. `awaiting_verification` 一律先查旧状态，不允许直接重发
4. `submitted` 不能被当作成功发布，只能被当作待确认
5. 只有拿到平台页面证据、列表证据或后台记录后，才允许进入 `published_verified`

## 8. 质量门禁

现有 `scripts/check_generated_article_quality.py` 已经能给出分数和问题项，本轮将其升级为硬门禁组件。

门禁规则：

1. 分数 `< 60`：直接阻断，状态写入 `quality_failed`
2. 存在任意 `fail` 项：直接阻断，状态写入 `quality_failed`
3. 分数 `60-79`：默认阻断，不自动发布，要求先修稿
4. 分数 `>= 80` 且无 `fail`：允许进入发布阶段

这样做的原因很直接：当前问题不是“发得不够快”，而是“弱稿进线过多”。先卡住差稿，再谈自动化。

## 9. 素材门禁

总控层在发布前检查：

1. `article.md` 或 payload 是否存在
2. `manifest.json` 是否存在
3. 封面图是否存在
4. 正文图数量是否满足 manifest 或 payload 定义
5. 平台标题变体文件是否存在；不存在则退回默认标题

如缺任一关键文件，状态写入 `asset_failed`，不进入发布脚本。

## 10. 去重与重复发布防护

### 10.1 指纹

统一指纹计算基于：

- 标题
- 摘要
- 正文 blocks

不把平台标题变体纳入主指纹。这样同一篇内容即使平台标题不同，也仍然能识别为同一篇稿件。

### 10.2 阻断原则

每个平台发布前都执行以下顺序：

1. 先查 `pipeline-state.json`
2. 再查该平台本地 records
3. 如果状态是 `submitted` 或 `awaiting_verification`，必须走“历史状态验证”
4. 只有验证结果明确为“未发布”，才允许继续提交

### 10.3 历史状态验证

这是本轮最关键的控制点。

规则如下：

1. 若平台状态为 `published_verified`：直接跳过
2. 若平台状态为 `awaiting_verification`：
   - 先检查最新后台记录或列表结果
   - 若已能证明发布成功，则更新为 `published_verified`
   - 若仍无法确认，则停止并返回，不允许再次提交
3. 若平台状态为 `publish_failed`：
   - 仅在失败证据明确是“未提交成功”时，才允许重试
4. 若平台状态缺失，但本地平台记录存在同指纹或同标题成功记录：
   - 视为 `duplicate_blocked`

公众号必须采用这套规则。此前重复发布的根因，就是在“状态不明”的时候把再次提交当成恢复手段。

## 11. 平台顺序与节奏

正式链路只处理三个平台，顺序固定为：

1. 今日头条
2. 知乎
3. 公众号

顺序原因：

1. 今日头条发布时间窗口更偏中午，且需要先验证列表状态
2. 知乎当前链路最稳，适合作为中段平台
3. 公众号最容易出现“待验证”状态，放在最后可以减少整条链被卡住时的回滚复杂度

## 12. 平台适配策略

### 12.1 今日头条

保留现有脚本的优势：

- 本地 duplicate record
- 列表页验证
- editor debug snapshot

需要增强：

1. `submitted` 不再被视作完成
2. 必须把列表验证结果回写到 `pipeline-state.json`
3. 若列表验证失败，则状态记为 `awaiting_verification` 或 `publish_failed`，不能写成成功

### 12.2 知乎

保留现有脚本的优势：

- 已有本地 fingerprint 去重
- 已支持正文图按 block 插入
- 已有发布后快照

需要增强：

1. 发布前先查统一状态文件
2. 本地 record 命中后要同步更新统一状态，而不是只在脚本内抛错
3. 成功发布后把链接、发布时间、标题变体写入统一状态

### 12.3 公众号

公众号是风险最高的平台。

需要新增硬规则：

1. 只要状态是 `awaiting_verification`，绝不允许自动二次提交
2. 发布前必须优先检查是否已经出现在历史发表记录中
3. 若后台历史已能证明成功发布，则只更新状态，不重复执行 submit
4. 若后台历史仍无法确认，则停在 `awaiting_verification`

公众号的目标不是“尽量自动重试”，而是“宁可停住，也不重复发”。

## 13. 总控脚本设计

建议新增一个 Python orchestrator，例如：

- `scripts/run_three_platform_pipeline.py`

选择 Python 的原因：

1. 现有质量脚本与日报工具都在 Python 中
2. 便于读写 JSON 状态文件
3. 便于串接现有 Node 发布脚本

它的执行流程如下：

1. 接收一个 payload 路径
2. 定位生成目录
3. 生成或刷新 `pipeline-state.json`
4. 运行质量检查
5. 运行素材检查
6. 载入标题变体
7. 依次调起今日头条、知乎、公众号脚本
8. 收集每个平台结果并回写状态
9. 输出一份统一 summary

## 14. 与 skills 的关系

本次安装的 skills 不直接“执行发布”，而是负责把内容前段做对。

推荐映射如下：

1. `dbs-content`
   - 用于生成前的内容诊断
   - 作用是减少低价值选题和空泛表达
2. `content-research-writer`
   - 用于资料整理、提纲和正文初稿
3. `Humanizer-zh`
   - 用于定稿前去 AI 味
4. `ian-xiaohei-illustrations`
   - 用于正文配图策略与单图生成
5. `guizang-social-card-skill`
   - 用于封面图

这些 skill 的产物最终要沉淀成文件和规则，再由总控链路消费。发布脚本本身不耦合 skill 运行时。

## 15. 实施步骤

按低风险顺序实施：

1. 先把质量脚本升级为可阻断模式
2. 新增统一 `pipeline-state.json` 读写模块
3. 实现总控脚本，只先接“预检 + 状态写入”
4. 接入今日头条脚本
5. 接入知乎脚本
6. 最后接入公众号脚本，并把“待验证即停止”作为硬规则
7. 用最近一篇真实稿件做 dry run

## 16. 验证标准

本轮实现完成后，至少满足以下验证条件：

1. 同一 payload 连续执行两次，总控层不会二次发布已验证成功的平台
2. 质量分 `< 80` 或存在 `fail` 项的稿件，不会进入发布脚本
3. 任一平台执行后，都能在 `pipeline-state.json` 找到清晰状态
4. 公众号在 `awaiting_verification` 状态下再次运行时，会停住并提示验证，而不是重发
5. 最终结果可以用一个 summary 文件解释“为什么发了 / 为什么没发”

## 17. 风险与取舍

主要取舍只有两个：

1. 自动化速度会变慢
2. 阻断次数会变多

这是刻意选择。当前最贵的错误不是“晚发 10 分钟”，而是“差稿发出”或“同平台重复发出”。

## 18. 结论

这次不是做一套新系统，而是给现有脚本加生产级总控层。

最关键的三条规则是：

1. 弱稿不进线
2. 状态不明确时先验证，不重发
3. 三个平台都写回同一个状态文件

只要这三条落地，当前链路就会从“能跑”提升到“可控”。
