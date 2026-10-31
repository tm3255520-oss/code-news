# 候选池（B站 DSH 自动采集）

拆解的输入是"哪些视频值得拆"。本文件定义**数据驱动候选池**：不靠员工主观选样，靠平台公开数据说话（摆脱"员工说的不一定精准"）。

## 采集器

`scripts/collect_bili_candidates.py`（确定性 🔵，无 LLM）

```bash
python scripts/collect_bili_candidates.py --config config.yaml --out-dir candidate_pool
# 或临时改关键词
python scripts/collect_bili_candidates.py --keywords "dsh 插件,dsh-std" --limit 20
```

## 数据流

```
关键词池搜索(B站免登录API) ─► 去重 bvid ─► view API 全指标
    └─ 自动作者发现(高播放作者) ─► 作者空间枚举 ─► 作者播放中位数(相对基线)
        └─ 作者空间里命中的 DSH 视频并入候选
筛选(播放/收藏率阈值) ─► candidates.json + candidates.csv + candidate_pool.md
```

## 关键设计

- **质量代理指标**（完播率无公开 API，用这些替代）：
  - 收藏率 = 收藏 ÷ 播放（资料价值，最重要）
  - 点赞率 = 点赞 ÷ 播放（共鸣度）
  - 投币率 = 投币 ÷ 播放（B站"真金白银"认可）
  - 评论率 = 评论 ÷ 播放（讨论度）
- **相对基线**：作者播放中位数 → `相对倍数 = 播放 ÷ 作者中位数`，≥5 倍为显著高于常态。
- **风控**：限速（config `request_interval_s`）+ 412 跳过不重试。
- **只抓公开数据**，不碰登录墙/付费内容。

## 产物解读

- `candidate_pool_*.md` 人读清单：按播放排序，直接看"哪条值得进拆解队列"。
- 拆解优先级建议：**播放高 + 收藏率高**（已被验证的爆款）> **播放中 + 收藏率高**（垂类精准，复刻价值大）> 播放低（反面教材）。
- 与拆解 skill 的衔接：选中的候选 → `extract_video_evidence.py` 产证据包 → `viral-video-breakdown` 出报告。
