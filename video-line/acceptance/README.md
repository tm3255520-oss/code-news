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
| `video-line/acceptance/landscape/deck.json` | 7352 | `723D697962AB3C17` |
| `video-line/acceptance/landscape/final.mp4` | 5401620 | `854335847072E659` |
| `video-line/acceptance/landscape/frames.jpg` | 30069 | `14AE70543C813046` |
| `video-line/acceptance/landscape/preview.mp4` | 3946857 | `D46E1B9692285643` |
| `video-line/acceptance/landscape/script.json` | 5490 | `CA87143558379F1A` |
| `video-line/acceptance/landscape/storyboard.check.md` | 105 | `922E90E8E9C6DDA4` |
| `video-line/acceptance/vertical/deck.json` | 7376 | `7F1AD2D0852BCE4F` |
| `video-line/acceptance/vertical/final.mp4` | 6421998 | `39C38D201184A072` |
| `video-line/acceptance/vertical/frames.jpg` | 57583 | `AB17F71CF5C670E0` |
| `video-line/acceptance/vertical/script.json` | 5490 | `CA87143558379F1A` |
| `video-line/acceptance/vertical/storyboard.check.md` | 105 | `922E90E8E9C6DDA4` |
| `video-line/acceptance/voice/voice_segmented.mp3` | 253725 | `27A2ADEE67A20D5B` |
| `video-line/acceptance/voice/voice_segmented.srt` | 1286 | `E4647F7FFD10EB34` |
| `video-line/acceptance/voice/voice_timeline.json` | 1914 | `65D5F57493C86ADE` |

两条成片同源：**同一份分镜、同一份 `script.json`、同一条音轨**，只有 `deck.json` 里的 `format` 不同。
成片规格：横屏 1440×1080 / 竖屏 1080×1920，均 27.800s、30fps、H.264 + AAC 48kHz 立体声，
质量门 `Check passed`、Contrast 136/136 WCAG AA。

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
| 合成 HTML | `3450E7BCF8DB2EA1` | 同哈希 | 逐字节一致 ✅ |
| 成片 MP4 | 5,401,620 B / `854335847072E659` | 5,396,074 B / `BE594EF60BC08572` | **差 0.1%，编码器层抖动** |

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
