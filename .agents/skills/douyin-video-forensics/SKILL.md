---
name: douyin-video-forensics
description: 抖音视频的「取证与实测」——把一条抖音视频拿到本地原始 MP4，并做出可量化的技术指纹（编码/码率/响度 LUFS/字幕形态/画面构成），用于拆解与对标。触发词：拆解这条抖音、分析这条视频怎么做的、抖音视频取证、扒一条抖音、测这条视频的响度/码率、对比我们和这条视频的画质。Do NOT use for：批量下载、二次搬运发布、绕过私密/付费内容（仅限用户已授权的公开视频）。
agent_created: true
---

# 抖音视频取证与实测

把一条抖音视频从「一个分享链接」变成「本地原始 MP4 + 一张可量化的技术指纹表」。

**核心价值**：抖音页面的 `<video src>` 是 `blob:` 协议（MSE），肉眼和常规抓包都拿不到真实地址 —— 本 Skill 记录了唯一走通的路径。**不要重走那 5 条死路。**

---

## 一、铁律

1. **只处理用户已给出链接的公开视频**。不批量爬取、不二次搬运发布。
2. **URL 带时间戳会过期**，拿到明文地址后**必须立即下载**，不要存起来下次用。
3. **带 `Referer: https://www.douyin.com/`**，否则防盗链拒绝。
4. **跑任何外部 CLI 前先清代理**：`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy <命令>`。IDE 注入的代理不转发外网，会导致 curl/ffmpeg 静默超时。
5. **bsk 绝不能 `capture_output=True`** —— `session start` 会遗留持有管道句柄的子进程，死锁到宿主 SIGTERM（**0.2.1 观察到；0.3.2 实测已不复现**，2026-10-08 探针 0.2s 正常返回 rc=0）。**保守做法照旧**：必须走 `tempfile.TemporaryFile()`。

---

## 二、取证路径（唯一走通的那条）

### ❌ 五条死路（别浪费时间去试）

| 尝试 | 结果 |
|---|---|
| curl `www.douyin.com/video/<id>` | 72,914 B JS 壳，`<script>` 里零命中视频 ID / desc / author |
| curl `iesdouyin.com` + 移动 UA | 32,566 B，`window._SSR_DATA` 里 `data:{}` **为空**（`renderInSSR:1` 但不注入数据） |
| `v.douyin.com` 短链 HEAD | 只拿到 302 跳转，能拿到视频 ID，但拿不到流 |
| bsk `screenshot` 抽帧 | `v.duration=null` / `videoWidth=0`，MSE 未起播，8 张帧全同（骨架态） |
| bsk `network` 缓冲 | 只有 `comment/list`、`im/user/info`、`query/user` 三类 XHR，**无视频流** |

### ✅ 正解：读 resource entries

MSE 分片虽然不暴露为 `<video src>`，但**浏览器 resource performance entries 里有完整 URL**。

```
① bsk session start            → 拿 sid
② bsk navigate <url> --session <sid> --wait-until domcontentloaded --timeout 40s
③ bsk wait-ms 6000ms           ⚠️ 不接受 --session
④ bsk evaluate "触发 v.play()"  --session <sid>
⑤ bsk wait-ms 4000ms
⑥ bsk evaluate <探针JS>         --session <sid>
⑦ bsk session stop <sid>
```

**探针 JS（核心，直接抄）：**

```javascript
performance.getEntriesByType('resource')
  .map(e => e.name)
  .filter(u => /mime_type=video_mp4|douyinvod|bytevod|play_addr/i.test(u))
```

筛出形如：
```
https://v26-web.douyinvod.com/<hash>/<ts>/video/tos/cn/.../?...&mime_type=video_mp4&qs=0&...
```

**同时也在 `document.documentElement.outerHTML` 里正则捞**，两份互为备份：
```javascript
document.documentElement.outerHTML
  .match(/https?:[^"'\s]{0,180}(?:\.mp4|douyinvod|bytevod)[^"'\s]{0,120}/g)
```

**过滤规则**：
- 要 `mime_type=video_mp4` 且路径含 `media-video`（视频轨）
- **滤掉** `media-audio` / `mime_type=video_mp4a`（那是音频轨，单独下载得不到画面）
- **滤掉** `douyin_pc_client.mp4`（那是客户端安装包广告，非视频本体）

### 下载

```bash
curl -sS -L --noproxy '*' -m 120 \
  -H "Referer: https://www.douyin.com/" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36" \
  -o raw.mp4 "<明文URL>"
```

**验真**：`ffprobe` 必须能读出 `width`/`height`，文件 > 100 KB。否则是防盗链页或过期。

---

## 三、文字信息提取（比重型抽帧可靠得多）

抖音的**全部文案与自动章节**在 `document.body.innerText` 里，`domcontentloaded` + **等 5-6 秒**后一次性拿到：

```javascript
document.body.innerText.slice(0, 4000)
```

能拿到：
- 标题、话题标签
- **「章节要点：共 N 个」+ 每章时间点与要点原文**（这是最好的结构证据）
- 简介、发布时间、作者与粉丝数
- 赞/评/藏/转 四项数据
- 「内容由AI生成」等平台标注
- 评论区首屏（含高赞负面反馈）
- 「推荐视频」区（同主题竞品与点赞数）

---

## 四、必须做的实测项（这才是取证的意义）

拿到 MP4 后，**逐项实测**，不要靠肉眼判断：

### 4.1 编码指纹

```bash
ffprobe -v error -show_streams -show_format -of json raw.mp4
```
必看：`codec_name` / `width`×`height` / `r_frame_rate` / `nb_frames` / 各轨 `bit_rate` / `pix_fmt` / `color_space` / `format_tags.encoder`（判 FFmpeg 版本）/ `format_tags.comment`（抖音内嵌 vid）

### 4.2 响度（EBU R128）——最有价值的一项

```bash
ffmpeg -hide_banner -nostats -i raw.mp4 -af "loudnorm=I=-14:TP=-1:print_format=json" -f null - 2>&1 | grep -A 14 '"input_i"'
```
读 `input_i`（整体响度 LUFS）/ `input_tp`（真峰值 dBTP）/ `input_lra`（响度范围 LU）

平台标准 **-14 LUFS / ≤ -1.0 dBTP**。偏离越大，观众越要调音量。

### 4.3 画面切点 —— 判断"合成"还是"幻灯片"

```bash
ffprobe -v error -f lavfi -i "movie=raw.mp4,select=gt(scene\,0.25)" -show_entries frame=pkt_pts_time -of csv=p=0 | wc -l
```
- **0 个硬切** → 全连续动画合成（motion graphics）
- **N 个硬切** → 图片/片段切换

### 4.4 音频结构 —— 判断有没有 BGM

```bash
# 静音段
ffmpeg -hide_banner -nostats -i raw.mp4 -af "silencedetect=noise=-45dB:d=0.4" -f null - 2>&1 | grep silence_
# 声道相位相关（≈1.0 = 近单声道/人声主导；明显低于 1 = 宽幅立体声音乐）
ffmpeg -hide_banner -nostats -i raw.mp4 -af "aphasemeter=video=0,ametadata=print:key=lavfi.aphasemeter.phase:file=-" -f null - 2>&1 | grep phase
# 语谱质心（人声约 500-1500 Hz 主导）
ffmpeg -hide_banner -nostats -ss 25 -t 3 -i raw.mp4 -af "aspectralstats=measure=centroid,ametadata=print:key=lavfi.aspectralstats.1.centroid:file=-" -f null - 2>&1 | grep centroid
```

### 4.5 画面构成判读（关键推理）

**低码率 + 高分辨率 = 画面高度平坦 = 合成图形，不是实拍。**

判据：`视频轨码率 / 像素数`。
- 1440×1080 @ **206 kbps** → 8.5 KB/帧 → **只可能是纯色底+文字+网格**
- 同分辨率实拍通常需要 3–8 Mbps

**反过来**：**高码率但画面糊** → 源图小、放大倍数高 → 素材层出了问题（这是"图片幻灯片"产线的典型病灶）。

### 4.6 抽帧与读字

```bash
# 总览（先看全貌）
ffmpeg -y -i raw.mp4 -vf "fps=1/4,scale=430:-1,tile=4x4:padding=6:color=white" -frames:v 1 contact_sheet.png
# 分页总览（看清每张卡）
ffmpeg -y -i raw.mp4 -vf "fps=1/1.5,scale=470:-1,tile=5x4:padding=4:color=0x333333" -frames:v 2 sheet_%d.png
# 关键帧全分辨率
ffmpeg -y -ss 9.5 -i raw.mp4 -frames:v 1 -q:v 2 key/t9.5.png
# 字幕条序列（裁底部条带，逐句读）
ffmpeg -y -i raw.mp4 -vf "fps=1/1.2,crop=1260:96:92:828,scale=560:-1,tile=1x18:padding=2:color=0x888888" -frames:v 3 subA_%d.png
# 角落小字/署名放大（crop 参数按视频分辨率算）
ffmpeg -y -ss 9.5 -i raw.mp4 -frames:v 1 -vf "crop=200:110:20:10,scale=800:-1:flags=lanczos" corner_tl.png
```

**读字幕条是最省力的文案还原法** —— 一行一张图，比听写快且准。

**注意**：`tile` 出来的图要逐张 `Read`，一次读一张，不要指望一张图读全。

### 4.7 找模板署名（判断用哪个引擎做的）

**角落小字是最高价值证据。** 逐帧放大四角 + 底部下方带，常能找到：
- 模板名（如 `RESEARCH CARD` / `VERSION. CARD 4:3 / AUTO 2.0`）
- 页码系统（如 `N / 07`）
- 系列名（如 `AI KNOWLEDGE SERIES 001`）

**交叉印证**：模板署名的画幅标注（`CARD 4:3`）应与 ffprobe 实测分辨率一致。一致 → 署名可信。

---

## 五、输出产物

一个取证目录，至少含：

```
raw.mp4              原始视频（证据本体）
basic.txt            bodyText 全文（文案+章节+数据+评论）
grab_stream.log      明文地址探测记录
stream_*.json        resource entries 命中清单
contact_sheet.png    全片总览
sheet_*.png          分页总览
key/*.png            关键帧全分辨率
subA_*.png           字幕条序列
corner_*.png         角落实名放大
probe_*.py           取证脚本（可复用）
```

---

## 六、常见坑

| 坑 | 症状 | 解 |
|---|---|---|
| bsk 参数顺序错 | `error: ... cannot be used with '[URL]'` | `bsk <cmd> <位置参数> --session <SID> [标志]`，位置参数在前 |
| bsk `wait-ms` 多传 `--session` | 静默以 unexpected argument 失败 | 只传 `<DURATION>`，支持 `30s`/`1m`/`1500ms` 或裸整数（毫秒） |
| bsk `screenshot --file` | 截图不存在 | 是 **`--out <OUT>`** |
| 拿了 audio 轨 URL | 下载到只有声音的文件（ffprobe 无 width） | 滤 `media-audio`，要 `media-video` |
| 下载到客户端安装包 | 文件是 `douyin_pc_client.mp4` | 正则命中时排除 |
| 文件小但 HTTP 200 | 防盗链页 | 补 `Referer` + 桌面 UA |
| ffmpeg 无输出 | 被代理拖住 | `env -u HTTP_PROXY ...` |
| bsk 结果空 | 页面没加载完 | `domcontentloaded` **不够**，要再 `wait-ms 5000ms` |

---

## 七、边界

- 只做**取证与实测**，不做内容复刻。复刻走 `viral-video-replicate`。
- 有完整拆解框架需求（爆款 DNA / 结构骨架 / 是否值得复刻）→ 用 `viral-video-breakdown`，本 Skill 作为它的**取证前置**。
- 私密内容 / 需登录才能看的内容 → 请用户直接提供本地文件，不绕过风控。
