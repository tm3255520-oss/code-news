# A5 vault 知识沉淀 —— 待 Hermes 落地

> 本会话对 vault（wiki/decisions、postmortems、workflows）无写权限（目录级 deny）。按项目"一个文件一个写者"分工，以下沉淀物由 **Hermes** 写入 vault 对应目录。

## 1. decisions（待 Hermes 复制到 `wiki/decisions/2026-08-25-爆款视频拆解管线立项.md`）

```markdown
---
类型: 决策
标题: "爆款视频拆解管线立项与选型"
一句话定义: "以 guozhi-video-breakdown 为方法论基座 + 自建四辐条，落地 B站 DSH 爆款拆解管线；8 样本校准证明判断与实际数据对齐。"
来源: ["code-news/research/dsh-std-video-analysis/", "用户需求：复刻爆款/分析爆款"]
创建日期: "2026-08-25"
最后更新: "2026-08-25"
状态: 稳定
标签: ["爆款分析", "DSH", "视频拆解", "B站", "管线"]
---

## 背景
用户要掌握"复刻爆款 / 分析爆款"能力，且摆脱对员工主观选样的依赖，要求数据驱动。

## 决策
1. 方法论基座：guozhi-video-breakdown（MIT，证据优先+10维拆解+复刻边界+输出模板）。
2. 自建四辐条：L4 数据门（防伪爆款）、图文TTS资讯视频专属六维、选题信息差判断、来源可溯。
3. 数据源：B站全链路免登录；DSH 内容首发 B站。
4. 两步走：拆解（前置，含验证）→ 复刻（后续）。

## 理由
- B站搜索/统计 API 免登录可用，DSH 赛道有真爆款（鱼皮 116.9 万）。
- 8 条样本拆解判断与实际数据完全对齐；L4 数据门正确拦截伪爆款。
- 同一条 dsh-std 视频头条 78 vs B站 3.7 万（470 倍，平台决定上限）；"读公告"内容集体扑街。

## 结果
- 管线跑通：viral-video-breakdown skill + 每日定时采集（dsh-candidate-pool-daily）+ 8 样本校准集。
- 代码：code-news commit 20600c21；tool_registry 注册 video_breakdown_skill。
```

## 2. postmortems（待 Hermes 写入 `wiki/postmortems/2026-08-25-viral-breakdown-pipeline.md`）

叙事要点（供 Hermes 扩写）：
- **现象**：B站视频抓取在沙箱多次失败：CDN TLS EOF、403 Forbidden、空间 API 412/-352、定时采集 175s 超时。
- **根因**：① python urllib 对 B站 CDN TLS 握手不稳 → curl 兜底；② 所有 B站 请求必须带正确 Referer（否则 403）；③ tesseract 子进程不继承局部 env 的 TESSDATA_PREFIX；④ 采集器候选太多 + 每候选限速 → 超时，需 max_stat_candidates 上限；⑤ 空间 API 需登录态/干净 IP，沙箱被风控 → 精确中位数只能宿主机。
- **学到了什么**：提炼为下方 workflows 硬规则。

## 3. workflows（待 Hermes 提炼到 `wiki/workflows/`，建议新建 `viral-analysis.md`）

硬规则（MUST）：
1. B站 下载：多清晰度轮询 + curl 兜底；所有请求带 `Referer: https://www.bilibili.com/video/{bvid}`。
2. tesseract 子进程必须显式传 `TESSDATA_PREFIX`（env）。
3. 定时任务命令必须能在沙箱单命令窗口（≤175s）内跑完；采集类脚本要加处理上限 + 分批落盘。
4. B站 空间 API（作者中位数）需登录态/干净 IP；沙箱降级"搜索采样近似（偏高偏保守）"，精确值走宿主机。
5. 转录校稿 = LLM + 确定性术语兜底替换（两层保证）；术语表放 skill references/video-asr-correction.md。
6. 爆款判断：高基线大作者用"≥3 倍中位数 + 绝对量达标"双条件，不用"≥5 倍"一刀切。

## 附带（也可让 Hermes 写入 decisions 关联）

- 校准证据与报告：`code-news/research/dsh-std-video-analysis/calibration/`（8 样本）
- 决策支持材料：`Phase2校准结论.md`、`author_medians.json`
