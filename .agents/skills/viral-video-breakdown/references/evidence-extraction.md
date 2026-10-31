# 证据提取（Evidence Extraction）

确定性步骤，全部走脚本（🔵）。本文件描述证据包的结构、来源与工具链；执行入口是 `scripts/extract_video_evidence.py`。

## 证据包结构

```text
<out_dir>/
├─ meta.json          # 平台/标题/作者/时长/发布时间/播放/互动/标签/封面URL
├─ video.mp4          # 视频本体（若可下载；720p 优先，失败降级）
├─ audio.wav          # 16k 单声道音频（ffmpeg -vn -ac 1 -ar 16000）
├─ transcript.txt     # 旁白逐句转写（带时间码 [start-end] text）
├─ frames/            # 每 3s 一帧（640 宽 jpg）
├─ contact_sheet.jpg  # 全部帧拼成的故事板（若有 sprite 则直接用平台 sprite）
├─ frames_ocr.md      # 每帧 OCR 出的画面文字（tesseract chi_sim）
└─ manifest.json      # 各证据项状态：ok / missing + error（失败跳过标记）
```

## 头条/西瓜（Toutiao/Xigua）专用链路【已验证 2026-08-25】

头条 PC 页是反爬壳（SSR 只有 JS 壳），**不要直接抓 www.toutiao.com/video/{id}/**。正确链路：

1. **取元数据**：用移动 UA 抓 `https://m.toutiao.com/video/{id}/`，HTML 的 script 里有 URL-encoded JSON，含 `articleInfo`：
   - `title / content / mediaUser(作者,粉丝数,视频数) / videoDuration / videoPlayCount / commentCount / diggCount / publishTime / playAuthTokenV2 / posterUrl / bizTag / isOriginal`
2. **换播放地址**：`playAuthTokenV2` 是 base64，解码后得 `GetPlayInfoToken`（AWS SigV4 签名串），直接 GET `https://vod.bytedanceapi.com/?{签名串}`，返回 JSON 的 `Result.Data.PlayInfoList[]` 里有各清晰度 `MainPlayUrl`（mp4 直链）与 `BigThumbs`（sprite 缩略图）。
3. **下载**：选 720p 直链下载 mp4（注意 URL 有过期时间，过期需重取）。
4. 若无移动页/接口变更：降级用 yt-dlp 尝试，再失败则请用户给本地文件。

> 注意事项：签名串内 `X-Amz-Expires=87840`（约 24h）；vod 返回的播放 URL 同样有时效。链接都不过期后重跑。不绕过风控，失败就标 `missing`。

## 通用平台链路（yt-dlp 兜底）

- 抖音/小红书/B站/视频号：先 `yt-dlp --dump-json` 取元数据，再 `yt-dlp -f best` 下载。
- 抖音等可能要求登录态：用 BSK/浏览器会话或请用户导本地文件，**不反复绕过**。

## 音频与帧

```bash
ffmpeg -y -i video.mp4 -vn -ac 1 -ar 16000 audio.wav
ffmpeg -y -i video.mp4 -vf "fps=1/3,scale=640:-1" -q:v 4 frames/f_%03d.jpg
```

## OCR（画面文字）

- 依赖：`tesseract` + `chi_sim.traineddata`（需显式 `TESSDATA_PREFIX`）。
- 每帧：`tesseract <frame> stdout -l chi_sim --psm 6 --dpi 96`。
- 产出 `frames_ocr.md`：`- t=N s | <ocr文本>`。OCR 噪声大时只取可读句子，其余标 `[画面噪声]`。

## 转写（旁白）

- 首选遵循项目 `video-pipeline.md` 铁律：**Whisper large-v3-turbo 粗转录 + LLM 校稿**（术语表纠错）。
- 模型/后端可配置（见 `config.example.yaml`：`whisper.model_name` / `whisper.model_dir`）。本 Skill 内转写用 faster-whisper 封装，支持本地目录加载模型。
- 校稿：在拆解报告前由 LLM 做一轮术语纠错（DeepSeek Harness、dsh-std、adapter 等专名），并把繁体→简体。
- 转写失败/无音频 → 标 `missing`，机制层不作风口播断言。

## 缺证据的诚实规则

| 缺什么 | 报告怎么标 |
|---|---|
| 无视频/帧 | 画面与剪辑维度标"未知"，不做视觉断言 |
| 无旁白/字幕 | 口播/金句维度标"未知"，不做文案断言 |
| 无互动数据 | 只基于内容机制推断"可能为什么火"，标"推断" |
