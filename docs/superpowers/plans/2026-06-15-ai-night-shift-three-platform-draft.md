# AI Night Shift Three-Platform Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new June 15 working draft for the “AI 接夜班” topic, generate platform-specific copy for 公众号 / 知乎 / 今日头条, refresh the image set, and pass preflight without triggering formal publish.

**Architecture:** Keep one shared fact base, but stop mutating the already-published June 5 slug. First add platform copy override support to the preflight pipeline so it can generate per-platform `title + summary + opening blocks`. Then fork the old article into a new slug, rewrite the content and image assets there, and run preflight-only against the new payload.

**Tech Stack:** Python 3.11, `unittest`, JSON payload files, Markdown article artifacts, local preflight pipeline, local image assets under `.tmp/generated`.

---

## File Map

- Modify: `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py`
  - Add platform copy override loading and application on top of title variants.
- Modify: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_three_platform_pipeline.py`
  - Add regression coverage for per-platform `summary` and opening-block overrides.
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json`
  - New base payload for today’s working draft.
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\article.md`
  - Shared fact-base article for the new slug.
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body.txt`
  - Plain-text body copy synced with the new article.
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\title-variants.md`
  - Platform-specific title candidates.
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\platform-copy.json`
  - Platform-specific `summary` and opening-block overrides.
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\manifest.json`
  - Image insert map and artifact metadata for the new slug.
- Create or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\cover.png`
- Create or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-01.png`
- Create or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-02.png`
- Create or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-03.png`

### Task 1: Add Platform Copy Override Support To Preflight

**Files:**
- Modify: `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py`
- Test: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_three_platform_pipeline.py`

- [ ] **Step 1: Write the failing test for summary and opening overrides**

```python
    def test_run_preflight_applies_platform_summary_and_opening_overrides(self) -> None:
        (self.generated_dir / "platform-copy.json").write_text(
            json.dumps(
                {
                    "toutiao": {
                        "summary": "早上打开电脑前，AI 已经先把日报和待跟进整理好了。",
                        "opening_blocks": [
                            "你早上打开电脑前，日报、分类和待跟进已经先跑完一轮了。",
                            "这才是这轮 AI 最该比的能力：不是更会答，而是能不能稳定接住一条流程。",
                        ],
                    },
                    "zhihu": {
                        "summary": "为什么说更有价值的 AI，不是更会回答，而是会自己跑流程？",
                        "opening_blocks": [
                            "如果一个 AI 每次都要等你开口，它更像高级搜索框。",
                            "如果它能按节奏自己整理、归类、提醒和回传，它才开始接近真正的工作伙伴。",
                        ],
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        run_preflight(self.payload_path, min_score=0)

        toutiao_payload = json.loads(
            (self.generated_dir / "platform-payloads" / "toutiao.json").read_text(encoding="utf-8")
        )
        zhihu_payload = json.loads(
            (self.generated_dir / "platform-payloads" / "zhihu.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            toutiao_payload["summary"],
            "早上打开电脑前，AI 已经先把日报和待跟进整理好了。",
        )
        self.assertEqual(
            toutiao_payload["article_blocks"][:2],
            [
                "你早上打开电脑前，日报、分类和待跟进已经先跑完一轮了。",
                "这才是这轮 AI 最该比的能力：不是更会答，而是能不能稳定接住一条流程。",
            ],
        )
        self.assertEqual(
            zhihu_payload["summary"],
            "为什么说更有价值的 AI，不是更会回答，而是会自己跑流程？",
        )
```

- [ ] **Step 2: Run the test to verify current behavior fails**

Run:

```powershell
python -m unittest tests.scripts.test_run_three_platform_pipeline.PipelinePreflightTests.test_run_preflight_applies_platform_summary_and_opening_overrides -v
```

Expected: `FAIL`, because current `write_platform_payloads()` only replaces `title`.

- [ ] **Step 3: Implement JSON override loading and opening-block replacement**

Add these helpers near `load_title_variants()` and `write_platform_payloads()`:

```python
def load_platform_copy_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def split_lead_blocks(article_blocks: list[str]) -> tuple[list[str], list[str]]:
    lead: list[str] = []
    rest: list[str] = []
    hit_heading = False
    for block in article_blocks:
        if not hit_heading and ("、" in block[:4] or block.startswith("一、") or block.startswith("1.")):
            hit_heading = True
        if hit_heading:
            rest.append(block)
        else:
            lead.append(block)
    return lead, rest


def apply_platform_copy(
    payload: dict[str, Any],
    platform: str,
    variants: dict[str, list[str]],
    overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    next_payload = dict(payload)
    next_payload["title"] = choose_platform_title(
        platform,
        variants,
        str(payload.get("title", "")).strip(),
    )
    platform_override = overrides.get(platform, {})
    if platform_override.get("summary"):
        next_payload["summary"] = str(platform_override["summary"]).strip()
    if platform_override.get("opening_blocks"):
        _, rest = split_lead_blocks(list(payload.get("article_blocks", []) or []))
        next_payload["article_blocks"] = [*platform_override["opening_blocks"], *rest]
    return next_payload
```

Then change `write_platform_payloads()` to load `platform-copy.json` from the generated directory and build each output payload through `apply_platform_copy(...)`.

- [ ] **Step 4: Run the focused test and the whole pipeline test file**

Run:

```powershell
python -m unittest tests.scripts.test_run_three_platform_pipeline.PipelinePreflightTests.test_run_preflight_applies_platform_summary_and_opening_overrides -v
python -m unittest tests.scripts.test_run_three_platform_pipeline -v
```

Expected: both commands `PASS`.

- [ ] **Step 5: Commit the code-only change**

```powershell
git add scripts/run_three_platform_pipeline.py tests/scripts/test_run_three_platform_pipeline.py
git commit -m "feat: support platform-specific preflight copy overrides"
```

### Task 2: Fork The Published June 5 Draft Into A New June 15 Working Slug

**Files:**
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\article.md`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body.txt`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\manifest.json`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\cover.png`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-01.png`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-02.png`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-03.png`

- [ ] **Step 1: Verify the old slug is unsafe to mutate**

Run:

```powershell
python -X utf8 -c "import json, pathlib; p=pathlib.Path(r'C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-05-ai-night-shift\pipeline-state.json'); data=json.loads(p.read_text(encoding='utf-8')); print(json.dumps(data['platforms'], ensure_ascii=False, indent=2))"
```

Expected: `zhihu.status == published_verified` and `wechat.status == published_verified`. This confirms the June 5 slug is historical record, not today’s working draft.

- [ ] **Step 2: Create the new working directory and copy only reusable binary assets**

Run:

```powershell
$src = 'C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-05-ai-night-shift'
$dst = 'C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value'
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "$src\cover.png" "$dst\cover.png" -Force
Copy-Item "$src\body-01.png" "$dst\body-01.png" -Force
Copy-Item "$src\body-02.png" "$dst\body-02.png" -Force
Copy-Item "$src\body-03.png" "$dst\body-03.png" -Force
```

Expected: four image files exist under the new slug before later replacement.

- [ ] **Step 3: Create the new base payload with the new slug**

Write `C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json` with this base structure:

```json
{
  "slug": "2026-06-15-ai-night-shift-workflow-value",
  "title": "AI 开始接夜班了：为什么真正值钱的，不是更会答，而是会自己跑流程",
  "summary": "这轮 AI 产品更新真正该看的，不是谁更会回答，而是谁开始能在后台接住重复流程。Notion 把 Custom Agents 定义成 24/7 处理 recurring work 的 teammates，Slack 把 AI step 放进 Workflow Builder，OpenAI 也把 schedule、shared agents 和 write approvals 写进 workspace agents。把这些信号放在一起看，AI 的价值判断正在从“会不会答”，切到“能不能稳定做”。",
  "cover": {
    "kicker": "AI NIGHT SHIFT",
    "meta": "2026.06.15 工作流价值判断",
    "title_lines": [
      "AI 开始接夜班了",
      "真正值钱的是会跑流程"
    ],
    "footer": "Workflow / Trigger / Schedule / Approval"
  }
}
```

- [ ] **Step 4: Verify the new payload points to a fresh slug**

Run:

```powershell
python -X utf8 -c "import json, pathlib; p=pathlib.Path(r'C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json'); data=json.loads(p.read_text(encoding='utf-8')); print(data['slug']); print(data['title'])"
```

Expected:

```text
2026-06-15-ai-night-shift-workflow-value
AI 开始接夜班了：为什么真正值钱的，不是更会答，而是会自己跑流程
```

### Task 3: Rewrite The Shared Fact Base And Platform Copy Files

**Files:**
- Modify: `C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\article.md`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body.txt`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\title-variants.md`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\platform-copy.json`
- Create: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\manifest.json`

- [ ] **Step 1: Replace the shared opening and keep one fact base**

Put this opening into both the payload base `summary` and the top of `article.md`:

```markdown
如果你最近还在比较哪个 AI 更会回答问题，你大概率已经比较错层了。今天真正拉开差距的，不再只是聊天窗口，而是后台有没有一条会自己跑起来的流程。

同样是 AI，有的只是在你开口之后给出一次答案，有的已经能在你不盯着的时候整理日报、归类问题、汇总进度、按节奏回传结果。真正开始值钱的，是后者。
```

Keep the factual core anchored to three product signals:

```markdown
一、Notion 把 AI 明确定义成 24/7 处理 recurring work 的 teammates
二、Slack 把 AI step 放进 Workflow Builder，让流程能按 schedule 或 event 自动跑
三、OpenAI 把 schedule、shared agents 和 write approvals 写进 workspace agents 标准能力
```

- [ ] **Step 2: End the shared draft with a concrete decision checklist**

Append this closing checklist to the shared article and make sure the same logic is reflected in `article_blocks`:

```markdown
真正值得长期留下的 AI，我现在只看 4 个问题：

1. 它能不能在你不盯着的时候继续跑，而不是每次都等你重新开口。
2. 它能不能接住固定频率或固定事件，而不是只在聊天框里临时发挥。
3. 它能不能把结果回传给团队，而不是只生成一段你还得手动搬运的文字。
4. 它有没有足够清楚的权限边界，确保“会做事”不会变成“乱做事”。
```

- [ ] **Step 3: Create exact title variants for the three platforms**

Write `title-variants.md` with this content:

```markdown
# 平台标题方案

## 今日头条
AI开始接夜班了：真正值钱的是会自己跑流程
AI不只是会聊天了，它开始替你盯流程
别只比谁更会答，先看AI能不能接夜班

## 微信公众号
AI 开始接夜班了：为什么真正值钱的，不是更会答，而是会自己跑流程
AI 不是更会聊天了，而是开始在后台替你把流程跑起来
这轮 AI 工具最该看的，不是谁更聪明，而是谁能稳定接住重复工作

## 知乎
为什么说现在更有价值的 AI，不是更会答，而是会自己跑流程？
AI 开始“接夜班”意味着什么？为什么 workflow 型能力比对话更重要？
为什么 Notion、Slack、OpenAI 都在把 AI 往 schedule 和 workflow 上推？
```

- [ ] **Step 4: Create exact per-platform summary and opening overrides**

Write `platform-copy.json` with this content:

```json
{
  "toutiao": {
    "summary": "你早上打开电脑前，如果日报、分类、待跟进已经先被 AI 跑完一轮，这才是这轮 AI 最值钱的变化。Notion、Slack 和 OpenAI 最近都在补同一层能力：让 AI 在后台按流程持续做事。",
    "opening_blocks": [
      "你早上打开电脑前，日报、分类和待跟进已经先跑完一轮了。",
      "这不是想象力竞赛，而是最近几家 AI 产品在真补的能力：不是更会聊天，而是开始能在后台接住流程。"
    ]
  },
  "zhihu": {
    "summary": "为什么说现在更有价值的 AI，不是更会回答，而是会自己跑流程？关键不在模型更聪明，而在 Notion、Slack、OpenAI 都开始把 schedule、workflow 和 approvals 做成默认能力。",
    "opening_blocks": [
      "如果一个 AI 每次都要等你开口，它更像一个高级搜索框；如果它能在固定节奏里自己整理、归类、提醒和回传，它才开始接近真正的工作伙伴。",
      "这也是为什么我更看重 workflow 型能力，而不是单次问答能力。最近 Notion、Slack 和 OpenAI 的产品动作，基本都在把 AI 从“会答”往“会做”推。"
    ]
  },
  "wechat": {
    "summary": "这轮 AI 产品更新里，最该看的不是谁更会回答，而是谁开始能在后台稳定接住一条流程。Notion、Slack 和 OpenAI 最近都给出了很明确的信号：真正值钱的 AI，正在从前台问答走向后台执行。",
    "opening_blocks": [
      "如果你最近还在比较哪个 AI 更会回答问题，你可能已经比较错层了。",
      "对团队和个人来说，更值钱的能力不是多一次漂亮回答，而是有没有一条流程，能在你不盯着的时候继续往前跑。"
    ]
  }
}
```

- [ ] **Step 5: Align the new manifest with the new slug and three body images**

Write `manifest.json` with these key fields:

```json
{
  "title": "AI 开始接夜班了：为什么真正值钱的，不是更会答，而是会自己跑流程",
  "summary": "这轮 AI 产品更新真正该看的，不是谁更会回答，而是谁开始能在后台接住重复流程。",
  "articlePath": ".tmp\\generated\\2026-06-15-ai-night-shift-workflow-value\\article.md",
  "bodyPath": ".tmp\\generated\\2026-06-15-ai-night-shift-workflow-value\\body.txt",
  "coverPngPath": ".tmp\\generated\\2026-06-15-ai-night-shift-workflow-value\\cover.png",
  "bodyImages": [
    {"title": "会答 vs 会做", "insertAfterBlock": 5, "pngPath": ".tmp\\generated\\2026-06-15-ai-night-shift-workflow-value\\body-01.png"},
    {"title": "触发 -> 执行 -> 回传", "insertAfterBlock": 10, "pngPath": ".tmp\\generated\\2026-06-15-ai-night-shift-workflow-value\\body-02.png"},
    {"title": "夜班 AI 的 4 个判断", "insertAfterBlock": 15, "pngPath": ".tmp\\generated\\2026-06-15-ai-night-shift-workflow-value\\body-03.png"}
  ],
  "sourceCount": 3
}
```

- [ ] **Step 6: Verify the three-platform copy is actually split**

Run:

```powershell
python -X utf8 -c "import json, pathlib; p=pathlib.Path(r'C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\platform-copy.json'); data=json.loads(p.read_text(encoding='utf-8')); print(data['toutiao']['summary']); print(data['zhihu']['summary']); print(data['wechat']['summary'])"
```

Expected: three different summaries, not the same text with tiny word swaps.

### Task 4: Replace The Image Set With Multi-Role Visuals

**Files:**
- Modify or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\cover.png`
- Modify or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-01.png`
- Modify or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-02.png`
- Modify or replace: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\body-03.png`

- [ ] **Step 1: Generate a new cover instead of reusing the old consulting-card template**

Use this prompt for `cover.png`:

```text
Editorial Chinese tech illustration, warm off-white background, late-night desk with a glowing workflow board still running after the human has left, strong sense of "AI taking the night shift", not SaaS template, not card collage, bold headline area, high contrast, modern magazine feel.
```

- [ ] **Step 2: Generate the comparison visual for body-01**

Use this prompt for `body-01.png`:

```text
Clean comparison board in Chinese, left side "会答" with a chat bubble and one-off prompt, right side "会做" with scheduled tasks, triggers, and status updates, simple annotated diagram, white background, editorial not corporate template.
```

- [ ] **Step 3: Generate the workflow visual for body-02**

Use this prompt for `body-02.png`:

```text
Chinese workflow diagram showing Trigger -> Execute -> Report Back, icons for schedule, classification, summary, sync, and delivery, minimal but vivid, clear reading order, no generic dashboard screenshot look.
```

- [ ] **Step 4: Generate the decision checklist visual for body-03**

Use this prompt for `body-03.png`:

```text
Chinese checklist poster with 4 questions for judging whether an AI can really take the night shift, numbered layout, editorial typography, not presentation slide style, warm neutral palette with one accent color.
```

- [ ] **Step 5: Verify the asset set matches the manifest**

Run:

```powershell
python -X utf8 -c "import json, pathlib; root=pathlib.Path(r'C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value'); print((root/'cover.png').exists()); print((root/'body-01.png').exists()); print((root/'body-02.png').exists()); print((root/'body-03.png').exists())"
```

Expected:

```text
True
True
True
True
```

### Task 5: Run Preflight-Only And Confirm The Draft Is Safe To Occupy

**Files:**
- Verify: `C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json`
- Verify: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\platform-payloads\toutiao.json`
- Verify: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\platform-payloads\zhihu.json`
- Verify: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\platform-payloads\wechat.json`
- Verify: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\pipeline-state.json`
- Verify: `C:\Users\Administrator\Documents\code-news\.tmp\quality-gates\2026-06-15-ai-night-shift-workflow-value.json`

- [ ] **Step 1: Run preflight-only against the new slug**

Run:

```powershell
python scripts/run_three_platform_pipeline.py C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json --preflight-only --min-score 80
```

Expected: JSON output with `mode = preflight`, `gate.status = passed`, and three `platformPayloads`.

- [ ] **Step 2: Verify the generated platform payloads are actually different**

Run:

```powershell
python -X utf8 -c "import json, pathlib; root=pathlib.Path(r'C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\platform-payloads'); names=['toutiao','zhihu','wechat']; payloads={name:json.loads((root/f'{name}.json').read_text(encoding='utf-8')) for name in names}; print(payloads['toutiao']['title']); print(payloads['zhihu']['title']); print(payloads['wechat']['title']); print(payloads['toutiao']['summary']); print(payloads['zhihu']['summary']); print(payloads['wechat']['summary']); print(payloads['toutiao']['article_blocks'][:2]); print(payloads['zhihu']['article_blocks'][:2]); print(payloads['wechat']['article_blocks'][:2])"
```

Expected:

1. Three different titles.
2. Three different summaries.
3. Three different opening-block pairs.

- [ ] **Step 3: Confirm the new pipeline state is clean and unpublished**

Run:

```powershell
python -X utf8 -c "import json, pathlib; p=pathlib.Path(r'C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\pipeline-state.json'); data=json.loads(p.read_text(encoding='utf-8')); print(json.dumps(data['qualityGate'], ensure_ascii=False, indent=2)); print(json.dumps(data['platforms'], ensure_ascii=False, indent=2))"
```

Expected:

1. `qualityGate.status == passed`
2. `toutiao.status == ready`
3. `zhihu.status == ready`
4. `wechat.status == ready`

- [ ] **Step 4: Stop after preflight and do not publish**

Do not run:

```powershell
python scripts/run_three_platform_pipeline.py C:\Users\Administrator\Documents\code-news\.tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json
```

The success condition for this plan is preflight pass + publish occupancy artifacts only. Formal publish remains out of scope.

