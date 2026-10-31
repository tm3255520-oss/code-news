---
name: viral-video-breakdown
description: 爆款视频拆解（证据驱动）——把一条视频拆成「为什么会火 + 结构骨架 + 可复刻机制 + 是否值得复刻」，并做爆款数据验证。触发词：拆解这条视频、分析爆款、为什么会火、拉片、黄金3秒、复刻脚本（拆解前置）、爆款判断。Do NOT use for：直接复刻（后续用 viral-video-replicate）、纯转写、长片影评、绕过登录墙/付费墙。
---

# 爆款视频拆解（证据驱动）

把一条爆款候选视频拆成**可判断、可复刻、可验证**的内容结构报告。本 Skill 只做「拆解与判断」，复刻由下游 `viral-video-replicate` 消费本报告的「爆款 DNA」与「底层公式」。

## 运行原则

1. **证据优先**：先看帧/contact sheet/字幕/转写/封面/标题/平台数据，再判断"为什么火"。缺什么证据就标"未知"，禁止脑补。
2. **三层分离**：客观事实（L1/L2）、推断机制（L3）、数据验证（L4）必须分栏，推断强制标注"推断"。
3. **学机制不抄表达**：拆解输出的是机制（人群/钩子/结构/信任/转化），不是逐字稿/截图/人设。
4. **防伪爆款**：未通过 L4 数据门的视频，一律标「未验证爆款」，禁止输出"值得复刻=是"。
5. **不绕过平台限制**：登录墙/付费墙/私密内容/风控拦截 → 请用户给本地文件/字幕/截图，不反复绕过。

## 工作流

> 颜色标记：🔵 纯脚本（确定性）｜🟡 LLM 辅助（语义，不决策）｜🔴 LLM 决策（价值判断）。目标 🔵≥80%。

1. **🔵 解析输入并提取证据**
   - 输入：URL 或本地视频/字幕/截图。
   - URL → 运行 `scripts/extract_video_evidence.py <url> <out_dir>`，产出证据包：
     `meta.json`（平台/标题/作者/时长/播放/互动/发布时间）、`video.mp4`、`audio.wav`、
     `frames/`（每 3s 一帧）、`contact_sheet.jpg`、`frames_ocr.md`（画面文字）、`transcript.txt`（旁白带时间码）。
   - 本地文件 → 直接走 音频/抽帧/OCR/转写 子步骤。
   - 依赖缺失（无 ffmpeg/tesseract/whisper）→ 标记该证据缺失，继续，不中断。

2. **🔵 证据包完整性检查**
   - 读 `references/evidence-extraction.md`，核对证据清单。
   - 在报告中显式声明：哪些证据拿到了、哪些缺失（如"无评论数据""转写失败"）。

3. **🟡 L2 结构层（事实+轻推断）**
   - 读 `references/viral-autopsy-framework.md` 的「分段图」「黄金3秒」。
   - 用时间线还原：钩子→痛点→方案→…→CTA；标题/封面公式；每段功能。
   - 产出：分段结构表 + 标题公式 + 开场钩子拆解。

4. **🔴 L3 机制层（推断，必须标注）**
   - 读 `references/viral-autopsy-framework.md` 十维表 + `references/info-video-dimensions.md`（资讯/图文TTS形态专属六维）。
   - 回答"为什么会火/会扑"：人群、情绪引擎、信息差、信任构建、留存设计、转化设计。
   - **每条机制结论前标"推断"**，并附支撑证据（来自 L1/L2 哪条）。

5. **🔵 L4 验证层（数据门）**
   - 读 `references/validation-gate.md`，按硬阈值判定：
     播放/互动绝对值、作者基线中位数、起量趋势、平台信号（推荐/热点/标签）。
   - 输出：`数据门：通过 / 未通过 / 数据不足` + 依据。

6. **🔴 是否值得复刻判断**
   - 综合 L2/L3/L4 输出结论：`值得复刻（条件）/ 不值得 / 待数据`。
   - 规则：L4 未通过 → 一律"待数据/不值得"，禁止"值得"。

7. **🟡 L5 产出拆解报告**
   - 读 `references/breakdown-output-template.md`，按模板生成**人读版**报告。
   - 模板包含：样本判断、证据包状态、为什么会火、前3秒钩子、分段结构、资讯专属维度、爆款DNA表、底层公式、数据门、能借鉴/不能抄、是否值得复刻。
   - 落盘：`<out_dir>/爆款拆解报告.md`。

## 资源路由

| 场景 | 读 |
|---|---|
| 自动发现候选（B站 DSH 视频+指标） | `references/candidate-pool.md` + 运行 `scripts/collect_bili_candidates.py` |
| 处理视频/URL/音频/字幕/截图 | `references/evidence-extraction.md` |
| 任何拆解/钩子/留存/机制分析 | `references/viral-autopsy-framework.md` |
| 图文/资讯/TTS 幻灯片型视频 | `references/info-video-dimensions.md` |
| 判断"是不是爆款/值得复刻吗" | `references/validation-gate.md` |
| 输出报告 | `references/breakdown-output-template.md` |
| 抽取证据 | 运行 `scripts/extract_video_evidence.py` |

## 失败处理（铁律）

- 单步失败 → 标记 `failed: true` + `error`，跳过继续，**禁止重试**。
- 证据缺失 → 报告里标"未知"，不编造。
- 平台下载失败 → 降级：请用户提供本地文件/字幕/截图。
