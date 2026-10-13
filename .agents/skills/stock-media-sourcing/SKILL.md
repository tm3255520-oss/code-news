---
name: stock-media-sourcing
description: 为自媒体产线「合法采购外部音乐 / 音效素材」的标准流程 —— 授权判定、渠道可达性、Mixkit 程序化抓取、按能量包络裁剪音效、落盘与授权台账。当用户说「攒素材」「攒曲库」「找商用 BGM」「找转场音效」「素材能不能商用」「这音乐会不会侵权」「平台曲库能不能用」「扩充素材库」「从 Mixkit/Pixabay 抓素材」时使用。含 5 类授权红线（平台曲库只覆盖单平台、剪映默认非商用、订阅制停订失效、CC BY-NC 商用禁用、Mixkit 排除电视电台）与「音效 > BGM」的反直觉优先级；**并含「音效时长必须跟转场时长配套」纪律（转场 ≥2s 时须备 ≥ 转场时长−0.3s 的音效）**。
agent_created: true
version: 1.2.0
tags: [stock-media, bgm, sfx, license, mixkit, sourcing, pipeline]
---

# 外部素材采购（音乐 / 音效）

> 适用：`D:\AI-VIDEO` 产线（以及任何要「多平台分发 + 商用」的自媒体场景）。
> 首次落地：2026-10-06，从 Mixkit 抓 5 首 BGM + 7 个音效；同批扩到 **10 首 BGM + 11 个音效**，0 元 0 失败。
> 母本文档：`config\素材库与授权指南.md`、`config\配乐方案.md` §5.3

---

## 一、先记住这条判断（与直觉相反）

**音效 > BGM，不是 BGM > 音效。**

| | BGM | 音效 |
|---|---|---|
| 能否自产 | ✅ 能（ACE-Step，Apache 2.0，1–2 分钟/首） | ❌ **不能** —— 音乐模型做不出「0.3 秒 whoosh」（要短促 / 单事件 / 无调性） |
| 该攒多少 | **10 首（5 档场景 × 2，一主一备）** | **11 个** |
| 外部渠道的价值 | 只是「质量天花板」+「系列一致性」 | **唯一来源，不可替代** |

→ 判断「该不该花时间攒」时：**能自产的少攒，不能自产的多攒。**

**数量饱和点**（防止收藏癖）：
- BGM 10 首（5 档场景 × 2，一主一备）｜音效 **11 个**｜频道主旋律 1 首
- 瓶颈从来不是「缺曲子」，而是「这条配哪首」→ 曲子越多，选曲越慢

> 🔴 **音效时长必须跟转场时长配套 —— 这条比「要几个音效」更重要。**
> 转场拉到 ≥2s 后，「个数够了」就失效：第一批 7 个里**最长的只有 1.95s**，
> 放进 3.0s 的转场窗里会「起了就没了」（前段响完、后段空着）。
> **判据**：转场 ≥2s 时，必须手头有 **≥ (转场时长 − 0.3s)** 时长的音效可用。
> 例：做 3.0s 转场 → 至少要有一条 ~2.7s 以上的音效。为此 2026-10-06 第二批
> 专补 3 个 **3s 级**转场音 + 1 个预告片冲击（11 = 7 + 4）。

---

## 二、🔴 授权：唯一会出事的地方

判据只有一个 —— **看授权类型，不看它「号称免费」**。

| 授权类型 | 商用 | 署名 | 出处 |
|---|---|---|---|
| CC0 / 公共领域 | ✅ | ❌ | FreePD、Pixabay 部分 |
| 平台自有免费授权 | ✅（**有范围限制**） | ❌ | Pixabay、Mixkit |
| CC BY | ✅ | ✅ **必须署名** | Freesound 部分、Incompetech |
| CC BY-NC | ❌ **禁用** | — | 大量「免费音乐」站 |
| 订阅制 | ✅ | ❌ | Epidemic Sound、Artlist |
| 平台内曲库 | ⚠️ **仅该平台** | — | 抖音、剪映、B站 |
| AI 生成 | ✅（看模型许可） | ❌ | ACE-Step（Apache 2.0） |

### 五个必踩的坑

1. 🔴 **平台自带曲库的授权只覆盖该平台** —— 抖音音乐库 / B站音频库是「站内使用」授权。
   一条视频分发 8 个平台时，在抖音用抖音曲库，发到 B站那段就没授权 → **平台曲库基本排除**。
2. 🔴 **剪映内置音乐默认「个人非商用」** —— 商用必须开会员 **且** 逐条筛「可商用」标记。
   即便这样，授权范围也建议只当站内用。
3. ⚠️ **订阅制停订后，旧视频里的曲子授权可能失效** —— 存量视频会连带出风险。
4. ⚠️ **Freesound 是 CC0 / CC-BY / CC-BY-NC 混合** —— 必须逐条看，只拿 CC0。
5. ⚠️ **Mixkit 的音乐明确排除「电视 / 电台 / 视频游戏 / CD / DVD」** ——
   做线上短视频（YouTube / 社交 / 播客 / 网站）落在允许区间；要上电视就得另找渠道。

---

## 三、渠道与实测可达性（2026-10-06）

| 渠道 | 内容量 | 商用 | 署名 | 能否程序化抓取 |
|---|---|---|---|---|
| **Mixkit 音乐** | 每类 29–36 首 | ✅ | ❌ | ✅ **可抓（推荐起步）** |
| **Mixkit 音效** | 每类 7–36 个 | ✅ | ❌ | ✅ **可抓** |
| Pixabay | 28 万+ / 12.8 万+ | ✅ | ❌ | ❌ **Cloudflare 拦截**（`Just a moment...`），需人工/浏览器 |
| Freesound | 数十万 | ⚠️ 逐条 | ⚠️ 逐条 | 需账号，人工 |
| 爱给网 CC 专区 | 中 | ✅ | 分栏标注 | 需登录 |
| 爱给网 版权配乐 | — | ✅ 含授权书 | ❌ | 付费 |

→ **Mixkit 是唯一「免版税 + 免署名 + 可商用 + 可程序化抓取」的渠道**，是零成本起步的执行渠道。

---

## 四、Mixkit 抓取实操

### 4.1 直链规律（关键）

```
音乐：https://assets.mixkit.co/music/<id>/<id>.mp3            ← 完整 mp3，非预览
音效：https://assets.mixkit.co/active_storage/sfx/<id>/<id>.wav  ← 完整无损 wav（优先）
      备选 https://assets.mixkit.co/active_storage/sfx/<id>/<id>-preview.mp3
```

- 音效**务必用 `.wav`**（`-preview.mp3` 是低码率预览）
- **部分 id 的 wav 会 403**（如 1143 / 788）→ 换同分类的备选 id，别死磕
- 必须带 **Referer**（`https://mixkit.co/free-stock-music/` 或 `/free-sound-effects/`）和正常 UA，否则可能被拒

### 4.2 列表页 → 候选清单

分类页路径（实测可用）：
```
音乐  /free-stock-music/tag/{cinematic,corporate,documentary,technology}
      /free-stock-music/mood/{relaxed,positive}
音效  /free-sound-effects/{whoosh,swoosh,transition,click,ding,impact,notification,pop,win,alarm}
```
> ⚠️ `tag/ambient`、`tag/uplifting`、`tag/calm`、`sound-effects/riser`、`sound-effects/logo`
> 这些路径 **301 重定向**（不存在），要用上表的实际路径。riser 类去 `swoosh`/`whoosh` 里翻，
> 片头标识去 `notification`/`ding`/`win` 里翻。

解析：每个素材是一个 `<div class="item-grid__item">` 块，块内含
`data-audio-player-item-id-value`、`<h2 class="item-grid-card__title">`、`meta-links__link`（标签）。
→ 脚本：`scripts/parse_mixkit.py`（用法 `python parse_mixkit.py <页面html目录> music|sfx`）

### 4.3 批量下载

→ `scripts/fetch_mixkit.py <manifest.json 路径>`（清单内置：**已含两批 = 10 首音乐 + 11 个音效**；
  改 `MUSIC` / `SFX` 两个列表即可。manifest 路径**必填**，无参数只打印用法、不下载不写盘）

---

## 五、🔴 音效必须裁剪（Mixkit 给的是含拖尾的完整版）

实测原始时长 vs 需求：

| 音效 | 原始 | 需求 | 结论 |
|---|---|---|---|
| whoosh | 1.76s（主体只到 0.75s，其后静音） | 0.4–0.8s | 裁 0.80s |
| ui click | 0.50s（**瞬态只有 30ms**） | 0.1–0.2s | 裁 0.15s |
| riser | **13.43s** | 1.5–3s | 换源（原曲结构是「渐强 0–7s」不适合） |
| logo sting | **8.97s（峰值在 4.33s）** | 1–2s | 换源 |

**方法：先测能量包络，再定裁剪点**（不要凭耳朵猜）：

1. `scripts/sfx_envelope.py <目录>` —— 按 20ms 窗口算 RMS 能量，转成**相对峰值 dB**
   （`20*log10(r/peak)`，本文件峰值 = 0 dB；**不是绝对 dBFS** —— 阈值 −50/−35 也是相对值），输出
   **能量起点 / >-50dB 终点 / >-35dB 终点 / 峰值位置** + 稀疏包络曲线
2. 按数据定 `ss`（起点，去掉前置静音）和 `duration`（取到 >-35dB 终点稍后一点）
3. `scripts/sfx_cut.py` 裁剪 + 淡入淡出 + 统一 `48kHz / stereo / pcm_s16le`
   （🔴 **默认 dry-run**：只打印输出根 + 将写的文件清单，**不落盘**；真写必须显式加 `--apply`）
4. **原始完整版存 `sfx\_raw\`** —— 日后想换裁剪点可重裁，不必重新下载

> 💡 判断「这个源能不能用」：看**峰值位置**。
> 峰值在开头（0.1–0.4s）= 正常击打类，可裁；
> 峰值在 4s+ = 结构是「长渐强」，裁了就废，**直接换源**。

---

## 六、落盘与授权台账

```
music\
├── library\{A_intro,B_background,C_transition,D_climax,E_outro}\   # BGM（按场景分）
│   └── _licenses\授权台账.md                                        # ★ 每素材一行
├── generated\                                                       # ACE-Step 自产
└── sfx\   + _raw\                                                   # 音效成品 + 原始存档
```

**台账字段**：`文件名 | 场景/用途 | 渠道 ID | 标题 | 许可类型 | 下载日期 | 直链`
- 免费免署名的（Mixkit / Pixabay）记清 **URL + 日期** 就够，不必截图
- 付费 / 授权书类**必须存凭证截图**到 `_licenses\screenshots\`

**两条纪律**：
- **绝不对 mp3 做重采样** —— mp3 已是编码格式，重采样要先解码再编码 = 引入第二次有损编码
  （违反产线「全程只有一次有损编码」）。保留原样，让 ffmpeg 解码时顺手重采样，免费且无损。
- **BGM 响度不用手动统一** —— 实测 5 首差 6.5 dB（-16.0 ～ -9.5 LUFS），
  `compose_long_video.py` 的 `measure_lufs()` 会逐首实测后自动补偿。

---

## 七、验收（必须做）

1. **格式**：`ffprobe` 逐个查 `duration / sample_rate / channels` → 音效必须 48000/stereo
2. **电平**：`ffmpeg -i x.wav -af volumedetect -f null -` 看 `max_volume`
   （⚠️ 别加 `-v error`，会把 volumedetect 的输出一起吞掉）
3. **端到端**：真跑一次合成，确认 `--bgm auto` 命中素材库、输出仍是 48k/stereo
4. 音效落点用 `--sfx-mode intro` 单点验证，别一上来就 `transitions` 全贴
5. **可闻长度**（🔴 判据**不能**写成「可闻终点 ≥95% 文件时长」——那是错的）：
   真人音乐正常以**淡出**收尾，实测最短一首 87.75s/99.4s = **88%** 属正常，
   与 ACE-Step 那种「15 秒后整段**数字静音**」是**两回事**。正确口径两条：
   - (a) 末段必须是**淡出**（逐窗 RMS 单调下降），**不是数字静音**（直接掉到 −120 / 精确 0）；
   - (b) 可闻长度 `M ≥ 3×` 成片时长（否则会被循环拼接、接缝听得见）。
   → 脚本：`scripts\batch2_verify.py`（格式 / 尾部性质 / 可闻长度一把过）
6. **A/B 差分**（证明「某条轨真的进了成片」的唯一硬证据）：
   A（含该轨）与 B（`--no-sfx`）**除该轨外完全同源**，比较 **loudnorm 之前**的原始混音
   → 残差 `A−B` **就是该轨本身**。落点误差应 ≤ 0.1s、且**无多余残差**。
   → 脚本：`scripts\sfx_diff_check.py <A.wav> <B.wav> 2.5 4.0 ...`
   （锚点写**裸秒数**或 `anchor=秒` 均可，两种都接受）

> 🔴 **使用纪律**：知识口播视频**不要每个转场都贴音效**。
> 30 秒 7 个转场全加 = 廉价感。建议**片头 1 个 + 全片最多 1–2 个重点强调**。
> 脚本默认 `--sfx-mode transitions` 只是功能完整性，**不是推荐用法**。

---

## 八、相关文件

- `config\素材库与授权指南.md` —— 授权母本（8 节）
- `config\配乐方案.md` §5.3 / §6.6 —— 落盘位置 + 音效轨用法
- `music\library\_licenses\授权台账.md` —— 台账本体
- skill `ffmpeg-audio-tracks` —— 音轨怎么混（本 skill 只管「素材从哪来、能不能用」）
