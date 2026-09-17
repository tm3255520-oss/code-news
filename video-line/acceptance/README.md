# 验收基准（入库）

这一目录放的是**这段视频生成环节的验收基准成片**——两条：横屏（归档画幅）与竖屏（投放画幅）。
它们入库的原因只有一个：**工作区万一丢了/被改坏了，还能拿它对比、还能复现**。

## 边界（别把它当垃圾桶）

| 入这里 | 不入这里 |
|---|---|
| 每个画幅**一条**基准成片（+ 它的输入与校验报告） | **每一期的成片**（那些留在 `renders/`，按仓库惯例不入库） |
| 与这份基准配套的配音（让复现不需要联网重新配音） | 中间件、抽帧过程图、临时样片（除基准样片） |

`video-line/.gitignore` 仍然忽略 `renders/` 与 `assets/`；本目录是**有意放行的例外**。

## 内容与指纹

| 文件 | 字节 | SHA256（前 16） |
|---|---|---|
| `video-line/acceptance/landscape/deck.json` | 8209 | `3AFFB87C59669D32` |
| `video-line/acceptance/landscape/final.mp4` | 6773262 | `A7A8324873F31C39` |
| `video-line/acceptance/landscape/frames.jpg` | 27926 | `3040F8CFD3F45AC3` |
| `video-line/acceptance/landscape/preview.mp4` | 3991529 | `D8A1C98A091DF1A4` |
| `video-line/acceptance/landscape/script.json` | 6123 | `EBB4E61F4FB2B47D` |
| `video-line/acceptance/landscape/storyboard.check.md` | 105 | `A5614186058BAB94` |
| `video-line/acceptance/vertical/deck.json` | 8208 | `339461967F293D70` |
| `video-line/acceptance/vertical/final.mp4` | 8004600 | `CDBBDECFABC3F8D4` |
| `video-line/acceptance/vertical/frames.jpg` | 54409 | `B2A3FCE16660C32A` |
| `video-line/acceptance/vertical/script.json` | 6123 | `EBB4E61F4FB2B47D` |
| `video-line/acceptance/vertical/storyboard.check.md` | 105 | `A5614186058BAB94` |
| `video-line/acceptance/voice/voice_segmented.mp3` | 294069 | `E5F3DF0A93219615` |
| `video-line/acceptance/voice/voice_segmented.srt` | 1445 | `831709965B2976CC` |
| `video-line/acceptance/voice/voice_timeline.json` | 2149 | `30D03795BCBF2B24` |

**2026-09-17 重记**：分镜加了第 9 镜（末卡 CTA：收藏 + 关注），全片 27.800s → **32.470s**，
9 张卡，质量门 `Check passed` / **Contrast 143/143** WCAG AA。上表为新一轮的指纹。

两条成片同源：**同一份分镜、同一份 `script.json`、同一条音轨**，只有 `deck.json` 里的 `format` 不同。
成片规格：横屏 1440×1080 / 竖屏 1080×1920，均 **32.470s**、30fps、H.264 + AAC 48kHz 立体声，
质量门 `Check passed`、Contrast **143/143** WCAG AA。

## 怎么复现（离线，不需要重新配音）

```powershell
cd C:\Users\Administrator\Documents\code-news

# 横屏
$out = "$env:TEMP\rebuild-landscape"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item video-line\acceptance\voice $out\voice -Recurse -Force
python scripts\build_card_video.py --script video-line\acceptance\landscape\script.json --out $out --skip-tts

# 竖屏
$out2 = "$env:TEMP\rebuild-vertical"
New-Item -ItemType Directory -Force -Path $out2 | Out-Null
Copy-Item video-line\acceptance\voice $out2\voice -Recurse -Force
python scripts\build_card_video.py --script video-line\acceptance\vertical\script.json --out $out2 --skip-tts --format vertical
```

`--skip-tts` 会复用 `<out>\voice\` 里的配音与时间轴，所以**配音先行推出来的卡片时长与字幕轴逐字节可复现**；
生成的合成 HTML 与 `video-line/index.html` 也逐字节一致（已实测）。

**但渲染出的 MP4 不是逐字节确定的**。实测同一输入重渲：

| 产物 | 基准 | 重渲 | 结论 |
|---|---|---|---|
| 合成 HTML | `22FCECE2C8D0E79C` | 同哈希 | 逐字节一致 ✅（2026-09-17 重验，横屏 `deck.json` → `video-line/index.html`） |
| 成片 MP4 | 6,773,262 B / `A7A8324873F31C39` | 5,396,074 B / `BE594EF60BC08572` | **编码器层抖动**（"重渲"列是 2026-09-16 在上一版基准上实测的，只用来证明 MP4 不逐字节确定，不是这一版的对照） |

所以基准成片用来做**规格与目视比对**（时长、分辨率、帧率、音轨、每张卡的起止、画面观感），
**不要拿它的哈希去要求"重渲必须相等"**；要判定改动是否影响成品，看的是合成 HTML 与质量门，而不是 MP4 哈希。

只想重生成合成（不渲染）时，可以直接喂 `deck.json`：

```powershell
python -c "import sys,json,io; sys.path.insert(0,'scripts'); import build_card_deck as B; print(len(B.build(json.load(io.open('video-line/acceptance/landscape/deck.json',encoding='utf-8')))))"
```

横屏 `deck.json` 生成的 HTML **与 `video-line/index.html` 逐字节一致**（已实测）。

## 完整口径

这一段的不可变项、契约、参数依据、已知边界与改动纪律见技能文档：
`.agents/skills/knowledge-video-storyboard/references/视频生成环节-冻结资产.md`（五个 Agent 的 skill 根均可达）。
