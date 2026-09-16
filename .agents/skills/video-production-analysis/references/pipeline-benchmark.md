# 对标自己的生产线

当任务目标是"看别人怎么做 → 改良我们的产线"，加这一节。

## 做法

把报告第五节（可迁移工艺）逐条拆成"环节"，每行问三个问题：

```
环节 → 我们现有能力（写实现文件路径或"无"） → 缺口 → 改动项（写清楚改哪个文件）
```

## 表格模板

| 这条片子要求的环节 | 我们现状 | 判定 | 改动项 |
|---|---|---|---|
| 图文+TTS 合成 | | ✅ / 🟡 / ❌ | |
| 配音选型 | | | |
| 配音与画面节点对齐 | | | |
| 字幕层（烧录 + 关键词高亮） | | | |
| 视觉规范（配色/层级） | | | |
| 动效模板 | | | |
| 平台取视频 | | | |
| 数据门验证 | | | |

## 输出要求

1. **按投入产出比排序**，不要按视频顺序排。先改"投入小、观感影响大"的。
2. **每条改动项必须指名到文件**，写不出来的说明还没调研清楚，标成"待调研"，不许模糊成"优化一下"。
3. **不要让报告停在建议**。结尾给出"下一步先做哪一项"的单一推荐，并说明理由。

## code-news 产线的已知环节（写差距时的锚点）

| 环节 | 位置 |
|---|---|
| 证据提取（帧/音频/OCR/转写） | `.agents/skills/viral-video-breakdown/scripts/extract_video_evidence.py` |
| 逐帧视觉描述 | `scripts/video_scene_vision.py` |
| 爆款拆解分析 | `.agents/skills/viral-video-breakdown/` |
| 图文幻灯片合成 | `scripts/compose_slideshow_video.py` |
| 统一生成入口 | `scripts/codex_api_mcp.py` |
| 取视频（抖音等） | `scripts/fetch_video_with_browser.py` |
| 制作工艺反推 | `scripts/analyze_video_production.py` |
| 注册表 | `config/tool_registry.json` |

