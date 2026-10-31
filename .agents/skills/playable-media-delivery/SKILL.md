---
name: playable-media-delivery
description: 把「播不了」的视频/音频变成可播副本，并生成可筛选、可内联播放的画廊页；以及在产线里固化这一步的钩子写法。当用户说「这个视频打不开/播放不了」「打开来看是黑屏」「能不能处理一下让我能播」「我想通过播放确认质量」「转码成能播的」「FFV1/mkv 播不了」「输出目录里的片子看不了」「把这一步固化进产线」，或需要把评测产出整理成可浏览的播放页时使用。核心是「先按 容器×编码×像素格式 判能不能播 → 用带色彩范围参数的 ffmpeg 转码（音轨按流判断）→ 三件套验证 → 生成画廊 → 钩子固化且不破坏画质口径」，其中「显式指定 in_range/out_range」与「别一刀切 -an 丢音轨」是最容易漏的两步。
agent_created: true
version: 1.1.0
tags: [ffmpeg, transcode, h264, faststart, gallery, media, qc, pipeline-hook]
---

# 把「播不了」的素材变成可播副本 + 播放画廊（playable-media-delivery）

> 首次落地：2026-10-07。背景是 AI 视频产线的**中间片惯例** ——
> Wan2.2 分支输出 `ffv1-mkv`（无损、16 位、带 alpha），用于和 H3 做公平的逐像素画质比对；
> 但这类文件**浏览器 / Obsidian / 微信 / 剪映全都不认**，只有 VLC/mpv 能解。
> 这个坑在本项目**至少踩了两次**（报告 §二 的 55.7MB MKV；`output/h3bench/` 里 12 个 875MB 的 MKV），
> 所以固化成流程：**产出可以无损，交付必须可播。**
>
> v1.1（2026-10-07 晚）：补 ①**音轨按流判断**（原版只提了一句，实际是最大的隐蔽坑）；
> ②**固化进产线的钩子写法**（§七）；③**交付后资料整理纪律**（§八）。

---

## 一、第一步：判「到底能不能播」（不要凭扩展名猜）

**能播 = 容器 + 编码 + 像素格式三者同时满足。** 只看 `.mp4` 后缀会被骗。

| 容器 | 视频编码 | 像素格式 | 能不能播 | 说明 |
|---|---|---|---|---|
| mp4 | h264 | yuv420p | ✅ | 通用交付格式 |
| mp4 | h264 | yuv444p / 10bit | ⚠️ | 部分播放器不认（浏览器基本不支持 High 4:4:4） |
| mp4 | hevc | yuv420p | ⚠️ | 浏览器支持不稳定，别当通用交付 |
| **mkv** | **ffv1** | **gbrap16le** | ❌ | **无损中间片**。体积大是因为无损，不是画质高 |
| mkv | h264 | yuv420p | ⚠️ | 部分浏览器不认 mkv 容器 |

```bash
# 一次性看清真相
ffprobe -v error -show_entries stream=index,codec_type,codec_name,width,height,pix_fmt \
        -show_entries format=format_name,duration,size,bit_rate -of default=nw=1 in.mkv
```

**批量审计**：遍历目录 → 按 `(ext, vcodec, pix_fmt, 有无音轨)` 分组统计。
一眼就能看出「哪一组是播不了的」，不用逐个试。参考实现见 §五。

> 🔴 **判定纪律**：`codec_name=ffv1` 或 `pix_fmt=gbrap16le` → **直接判不可播**，不用去试。
> 反过来，`h264/yuv420p/mp4` 也要**实测解码**才能确认（下面 §三）。
>
> ⚠️ **`ffprobe` 参数坑**：`-select_streams v:0` 与 `-select_streams a:0` **同时写会互相覆盖**，
> 后一个生效 → 视频宽高/pix_fmt 读成空。要一次看清音视频，改用：
> `ffprobe -show_entries stream=codec_type,codec_name,pix_fmt -of json`（不带 `-select_streams`）。

---

## 二、转码：参数里的四个坑

### 标准命令（已在本机验证）

```bash
ffmpeg -y -v error -i in.mkv \
  -vf "scale=in_range=full:out_range=limited:out_color_matrix=bt709,format=yuv420p" \
  -c:v libx264 -preset slow -crf 14 \
  -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -movflags +faststart <有音轨就加 -c:a aac -b:a 192k，没有才加 -an> out.mp4
```

### 坑 ①：**必须显式写色彩范围**（最容易漏）

FFV1 中间片通常是 **`color_range=pc`（全范围）+ `color_space=gbr`（RGB）**，
而 yuv420p 交付格式是**有限范围（tv）**。不写 `in_range=full:out_range=limited`：

- 后果：画面**发灰、对比度被压扁**（或反向：暗部死黑、高光溢出）
- 而且**很难自查** —— 你得跟源并排看才发现

先探测源的范围再决定：

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=color_range,color_space,color_primaries,color_transfer -of default=nw=1 in.mkv
# 本机实测：color_range=pc / color_space=gbr / color_transfer=iec61966-2-1(sRGB)
```

### 坑 ②：**alpha 通道要先确认再丢**

`gbrap16le` 带 alpha。转 yuv420p 会丢掉它 —— 先确认是不是全不透明：

```bash
ffmpeg -v info -i in.mkv -vf "alphaextract,format=gray,signalstats,metadata=print:file=-" \
       -f null - 2>/dev/null | grep -E "YMIN|YMAX"
# YMIN=255 & YMAX=255  → 全不透明，丢掉无损失
```

### 坑 ③：**`-movflags +faststart` 不能省**

moov atom 默认在文件尾 → 浏览器/预览面板**要先下完整个文件才能播**，表现为「点了没反应/一直转圈」。
`+faststart` 把它挪到文件头。转完必须验证（见 §三）。

### 🔴 坑 ④：**音轨必须「按实际流判断」，不能一刀切 `-an`**（本条最隐蔽，v1.1 升级）

早先的单机转码脚本**一律写死 `-an`**（丢音轨，只转画面）。这在**无声的 Wan 上完全没问题**，
但一旦源是**音视频同一次生成**的模型（H3 就是），`-an` 会把 **评测的主角整条丢掉**，
而且**转码本身会「成功」**（无报错、文件正常），**极难发现**。

```bash
# 正确做法：先探测有没有音频流，再决定
ffprobe -v error -show_entries stream=codec_type,codec_name -of csv=p=0 in.mkv
# 结果里有 audio 行 → -c:a aac -b:a 192k ；没有 → -an（避免生成空音轨）
```

> 📌 **采样率也要注意**：H3 输出是 **32kHz**，拼到 48kHz 时间线**必须重采样**，否则变调/爆音。
>
> 🔴 **验证纪律**：转完的副本必须**回读一遍音频流**确认还在
> （本机实测 `acodec=aac` 才算过；只看"转码成功"没用）。

### crf 怎么选

- **交付/确认质量**：`-crf 14`（配合 `-preset slow`）足够，实测距转换天花板仅 0.42 dB
- 想更小：`-crf 18~20`，但先跑 §三 的 PSNR 确认没掉太多
- **不要用 `-qp 0`**：文件会涨 10 倍以上（本机实测 0.54MB → 7.7MB），且仍带转换损失，无意义

---

## 三、验证三件套（不给证据的「已转好」不算数）

| # | 验证项 | 命令 | 通过标准 |
|---|---|---|---|
| ① | **真能解码** | `ffmpeg -v error -i out.mp4 -f null -` | 退出码 0 且 **stderr 为空** |
| ② | **faststart** | 读文件头 64KB `find(b"moov")` | `moov` 出现在前 64KB 内 |
| ③ | **保真度** | 与源比 PSNR（**源要先过同一套 vf 滤镜**） | 与「天花板」相差 < 1 dB |
| ④ | **音轨还在**（源有音轨时） | `ffprobe -show_entries stream=codec_type` | 有 audio 流，且 codec 是 aac |

### ③ 的关键：必须跟「转换天花板」比，而不是跟「无损」比

RGB16 → YUV420 8-bit 这个**转换本身**就有损失（主要是色度 4:2:0 下采样），
拿它跟源比永远只有 ~37 dB，**这个数字本身不能说明转码好不好**。正确做法：

```bash
# 先算天花板：同一条 vf + 无损编码
ffmpeg -y -i in.mkv -vf "$VF" -c:v libx264 -qp 0 -an _ceiling.mp4
ffmpeg -i _ceiling.mp4 -i in.mkv -lavfi "[1:v]$VF[b];[0:v][b]psnr" -f null -
# 再算实际产出（同一条 vf 做参照系）
ffmpeg -i out.mp4 -i in.mkv -lavfi "[1:v]$VF[b];[0:v][b]psnr" -f null -
```

本机实测（WAN-BASE）：天花板 **37.99 dB**，crf14 产出 **37.57 dB** → **差 0.42 dB ＝ 视觉无损**。
`[Parsed_psnr] not matching timebases` 的警告可忽略（时间基不同，不影响均值）。

---

## 四、生成播放画廊（「通过播放确认质量」的最佳载体）

**为什么不做成"给一堆文件让用户自己双击"**：100+ 个文件逐个开播放器无法横向比较，
而"确认质量"本质是**对照**（塌陷档 vs 正常档、8 步 vs 50 步）。

画廊页要点：

1. **一张卡一段视频**：缩略图（poster）+ 关键元数据 + 原生 `<video controls>`
2. **`preload="none"` + poster**：100+ 个也秒开，点了才拉流
3. **把判读结论标在卡片上**（✅正常 / ❌塌陷 / —无音轨），复用产线已有的判读 JSON
4. **筛选**：家族（family）chip + 搜索框 + 「只看异常」开关
5. **顶部写清「怎么读」**：哪类是反例、哪些是正常现象（如 Wan 本来就没音轨）
6. **缩略图**：`-ss <dur*0.4> -frames:v 1 -vf scale=440:-2 -q:v 4`
7. 🔴 **卡片指向的必须是可播副本**：若某档有 `xxx_h264.mp4`，`src` 要指副本而不是原 mkv
   （否则画廊里那几张卡还是播不了 —— 这一条要**逐个核对**，别只统计"资源存在"）

```bash
# 缩略图（每个约 15–25 KB）
ffmpeg -y -v error -ss 1.2 -i in.mp4 -frames:v 1 -vf "scale=440:-2" -q:v 4 thumbs/name.jpg
```

> 📌 **文件名含中文**：HTML 里写中文即可，**不必手工 percent-encode**（浏览器会自动编码）。
> 但 `urllib` 等客户端脚本**必须手工 `urllib.parse.quote`**，否则抛 `UnicodeEncodeError`。
> 文件名纯 ASCII 时最省事 —— 缩略图/画廊的生成脚本可优先选 ASCII 名。
>
> ⚠️ **校验脚本注意**：`<img>` / `<source>` / `<br>` / `<meta>` 是 **void 元素，没有闭合标签**。
> 按常规「开闭标签配平」扫描会误报红色，别被吓到。

---

## 五、本机落地（可直接复用）

| 用途 | 路径 |
|---|---|
| 可播性审计脚本 | `D:/AI-VIDEO/scripts/_media_audit.py` |
| 批量转码（含验证） | `D:/AI-VIDEO/scripts/_media_transcode.py` |
| **产线固化钩子** | `D:/AI-VIDEO/scripts/ops_h3_bench.py` → `ensure_playable()` |
| 产线钩子运行日志 | `D:/AI-VIDEO/logs/h3bench/_playable_copies_<date>.txt` |
| 转码证据 | `D:/AI-VIDEO/logs/h3bench/_media_{audit,decodecheck,transcode_report}_20261007.txt` |
| 实战产物 | `D:/AI-VIDEO/output/h3bench/index.html`（121 段）+ `thumbs/` |
| 判读数据源 | `D:/AI-VIDEO/scripts/_final_rows_v2.json`、`D:/AI-VIDEO/logs/h3bench/_quiet_confound_cache.json` |

**浏览画廊时注意本地服务**：`<video>` 的相对路径在**直接用浏览器打开 html** 时天然可用；
若要在内置预览面板里播，需先起静态服务（否则相对资源可能 404）：

```bash
cd <目录> && python -m http.server 8765 --bind 127.0.0.1     # 用受管后台任务起，勿用 nohup &
```

---

## 六、纪律

- ✅ **产出可以无损，交付必须可播**：转码只**新增**副本，**原始中间片一律保留、不删**
- ✅ **口径写进文件名**：`xxx_h264.mp4`，一眼知道是转码副本
- ✅ **体积对比要有**：本机实测 875 MB → 8.8 MB（**100:1**），这个数字本身就是"无损格式不适合交付"的最好论据
- 🔴 **不要只报告"已转码"**：必须附 ①解码通过 ②faststart 通过 ③PSNR 距天花板 < 1 dB
  ④（源有音轨时）音轨还在 —— 四条证据
- ✅ **钩子开关化**：给个环境变量（如 `H3_PLAYABLE=0`）能一键关掉，方便出问题时旁路
- ✅ **ffmpeg 不在位时只警告不报错**：转码是**后处理**，绝不能因为它把整个评测批搞挂

---

## 七、把这一步固化进产线：钩子的正确写法（v1.1 新增）

**先说清什么不该做。** 根因往往是产线节点的**编码参数本身没错**
（如 `format: "video/ffv1-mkv"`，那是**为画质比对故意的**）。
所以：

> 🔴 **绝对不要直接改产线的输出编码参数**（把 `ffv1-mkv` 换成 `h264`）。
> 那会**污染画质基准** —— 之后所有 PSNR / 逐像素比对全部失效。
> **正确做法是「产出照旧无损 + 产出后补一步转码副本」。**

### 钩子挂在哪个位置

**收齐产出路径之后、写结果 JSON 之前。** 具体到本项目的 `run_one()`：

```
outs = [...从 /history 解析出的产出绝对路径...]
outs, play_recs = ensure_playable(outs)      # ← 钩子在这里
result["outputs"] = outs
result["playable_copies"] = play_recs
json.dump(result, ...)                       # ← 落盘
```

### 两条「零破坏」硬约束（这是能不能安全插入的关键）

**Ⅰ · 不要动 `outputs` 字段的语义。**
下游可能有一堆脚本按 `outputs[0]` 取视频（本项目有 4 处）。
你往里塞副本路径 → **统计口径立刻飘**。
→ **另开一个字段**（如 `playable_copies`）承载副本记录，`outputs` 原样返回。
   并且**失败分支也要补上同构的空字段**，否则聚合脚本读到 `None` 会算成脏数据。

**Ⅱ · 不要改编码器。** 见上。

### 钩子函数该长什么样（三段式）

```python
def ensure_playable(outs):
    if 开关关闭 or ffmpeg/ffprobe 缺失:      # ① 可旁路、可降级
        return outs, []
    recs = []
    for src in outs:
        meta = _probe_av(src)                # ② 探测（音视频流 + 编码 + 像素格式）
        if _is_playable(src, meta):          #    已经能播 → 跳过，不重复转
            continue
        dst = <同名> + "_h264.mp4"
        if os.path.isfile(dst):              #    幂等：副本已在就跳过
            continue
        cmd = [ffmpeg, ..., <按 meta 决定 -an 还是 aac aac>]   # ③ 才转
        ... 转完自检 decode + faststart，记入 recs
    return outs, recs                        # outs 原样！
```

### 落地必跑的四个用例（**只测「能转」是不够的**）

| # | 用例 | 期望 |
|---|---|---|
| 1 | **带音轨**的不可播源 | 转出 h264，且 **`acodec=aac`（音轨保住）** ← 最关键 |
| 2 | **无音轨**的不可播源 | 转出 h264，`acodec=None`（走了 `-an`） |
| 3 | **本来就能播**的 mp4 | `is_playable=True` → **跳过，产生 0 个副本** |
| 4 | **开关关闭**（`H3_PLAYABLE=0`） | 完全跳过，0 个副本 |

> 📌 用例 1 是最该测的：它正是"一刀切 `-an` 丢音轨"这个隐蔽 bug 的守门测试。
> 📌 用例 3 防的是"把好文件也重转一遍"（白耗时间还多一份冗余）。

---

## 八、交付之后的资料整理纪律（v1.1 新增）

转完码、做完画廊，**这一步最容易漏**，而且漏了会让下一轮审计白忙。

1. 🔴 **做完加工立刻回写主文档**：转码/画廊的成果（体积比、PSNR、画廊路径）
   **当天就要进运行小结与报告**。否则下一轮审计才发现"做了但没记"，等于这次加工对外部读者不存在。
2. 🔴 **不要凭文件名判断文件内容**。本项目的真实翻车：
   一张叫 `NATIVE-3tiers-compare` 的图被当成"音轨收敛图证"写进了日志，
   **放大核对后发现是画面帧格**；另一张叫 `H3-FRAMES-ROOTCAUSE` 的图名字来自
   **已被推翻的「帧数假说」**。
   → **引用任何图证前，先 `Read` 看一眼**；名字与内容不符的，要在索引里**标「历史假说」**。
3. 🔴 **判"是不是冗余副本"要用 md5，不能用名字**：
   本项目的真实翻车 —— 曾写「证据目录那 3 段 mp4 与 `samples/` 是不同档位、勿删」，
   **md5 核对后是完全相同**（三重冗余）。**移走前逐个 md5 比对**。
4. ✅ **两阶段清理**：冗余文件**先移入回滚区**（如 `D:/AI-VIDEO/_rollback_<date>/`），
   **观察一段无异常后再彻底删**。不要一步删掉。
5. ✅ **给混放目录写索引**：当一个目录同时装着「现行结论」和「已被推翻的历史假说」，
   必须写一个 `README.md`，**逐个标状态**（✅现行 / ⚠️历史假说），否则下一个人会误读。
6. ⚠️ **索引类文件的行尾要跟所在目录的惯例走**（本项目 `h3_evidence/` 的 md 是 LF，
   `logs/h3bench/` 的 md 是 CRLF）—— 写完**按字节核对一次**再收工。

---

## 九、本机踩坑（跨领域，但都会打断这一步）

- 🔴 **`robocopy` 在 Git Bash 里有两个坑**：
  ① **中文目标路径会被编码搞坏** —— robocopy 报"无效参数"或**静默什么都不做**，
  文件纹丝不动却看不到错误。→ **用 ASCII 路径**（含中文的目录名另外处理）。
  ② **`/MOV` 被 MSYS 当路径转换**，变成 `.../PortableGit/.../MOV` 并报"无效参数 #7"。
  → 必须 `export MSYS_NO_PATHCONV=1`。
  ```bash
  export MSYS_NO_PATHCONV=1
  robocopy "D:\\src" "D:\\dst" "file1.mp4" "file2.mkv" /MOV /R:0 /W:0 /NFL /NDL /NJH /NJS
  ```
- 🔴 **本机 Python / PowerShell 的 stdout 常被吞**（多次复发）：脚本"跑完了"但看不到输出。
  → **一律 `open(..., 'w').write(...)` 落盘，再用 Read 取**。
- 🔴 **不要用 `Add-Type`**（加载 .NET）—— 被安全策略直接拦死。
  需要 .NET 的活（如发到回收站）要写进 `.ps1` 文件；而 `.ps1` **只能用 ASCII 注释**
  （Write 工具写中文注释会与下一行代码合并 → 整脚本静默不执行）。
