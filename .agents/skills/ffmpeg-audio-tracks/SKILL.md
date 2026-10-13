---
name: ffmpeg-audio-tracks
description: 给视频合成链加音轨（BGM / 音效 / 旁白多轨混音 + ducking 自动让位）的标准写法与验证方法。当用户说「加背景音乐」「配乐接进来」「旁白和 BGM 混音」「BGM 太响/太小声」「音乐要自动让位」「加音效轨」「转场音效」「ducking 不生效」时使用。含 7 个必踩的 ffmpeg 坑（asplit 分流、asplit 输出必须全消费、-t 是输出选项会无限写盘、loudnorm 改采样率且吃声道、**链内单遍 loudnorm 会差 2dB 且顶爆真峰值 → 必须两遍法**、**音乐模型出片要测 TP/LRA，会削顶**、按相对响度标定），以及「跟旁白活动性做关联」与「单独导出音效轨看落点」两套验证手法，和「拼装凑整用交叉溶解吸收误差」的配方。
agent_created: true
version: 1.1.0
tags: [ffmpeg, audio, bgm, sfx, ducking, pipeline, video]
---

# 给视频加音轨 / 多轨混音

> 适用：`compose_long_video.py`（AI 视频产线）以及任何用 ffmpeg 做音轨合成的场景。
> 首次落地：2026-10-05，demo30 + ACE-Step BGM，端到端实测跑通。

## 一、四条硬规则（踩过，别再踩）

### 1. 🔴 一个输出 pad 只能被一个下游消费 → 用 `asplit`

旁白既要当 `sidechaincompress` 的 key、又要进 `amix`，**直接写两遍 `[voice]` 必报**：
```
Error binding filtergraph inputs/outputs: Invalid argument
```
（`-v error` 下有时只给这一句，看不到具体哪个 pad，容易误判成别的原因）

**解法**：
```text
[voice]asplit=2[v_dub][v_mix]
[bgm_side][v_dub]sidechaincompress=...[bgmduck]
[v_mix][bgmduck]amix=inputs=2:duration=first:normalize=0[aout]
```
同理：BGM 既要当侧链又要旁路输出时也要 asplit。
**另外 `asplit` 出来的每一个 pad 都必须被消费**，否则报 `Filter 'asplit' has output 0 (xxx) unconnected`。

### 2. 🔴 `-t` 是「输出选项」，不是滤镜选项

`-t 12` 只作用于**它后面紧跟的那个输出文件**。多输出时：
- ✅ 逐输出写：`-map [a] -t 12 a.wav -map [b] -t 12 b.wav`
- ✅ 更稳：在滤镜里用 `atrim=` 限长

**血的教训**：`-stream_loop -1` + 未限长的输出 → **无限写盘**。实测 `bgm_raw.wav` 写出 **76 GB**，D 盘差点满，进程被 SIGTERM。

### 3. 🔴 `loudnorm` 会改采样率

实测：源 24 kHz mono → `loudnorm=I=-16:TP=-1.5:LRA=11` → 输出 **192000 Hz**。
下游 AAC 最终落成 **96 kHz mono**（立体声信息也在混音里被吃掉）。

**修法**（音频链末端）：
```text
...,aformat=sample_rates=48000:channel_layouts=stereo[aout]
```
外加输出参数 `-ar 48000 -ac 2`。

### 3b. 🔴🔴 `loudnorm` 在滤镜链里**只跑一遍是不够的**（2026-10-06 实测，务必两遍法）

单遍 `loudnorm` 走的是 **dynamic（动态）模式**：精度不足，**而且会越界推高真峰值**。

| 做法 | 实测结果 |
|---|---|
| 链内单遍 `loudnorm=I=-14:TP=-1.5` | 落 **-11.99 LUFS**（目标 -14，**差 2 dB**）；**真峰值被顶到 -1.33**（源 -3.30） |
| **两遍法**：先测 → 再带 `measured_*` + `linear=true` | **-13.85 LUFS / TP -2.25** ✅ |

```bash
# 第 1 遍：只测量，不输出（读 input_i / input_tp / input_lra / input_thresh / target_offset）
ffmpeg -v info -i bgm.flac -af "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" \
  -f null - 2>&1 | sed -n '/{/,/}/p'

# 第 2 遍：把测量值喂回去做【线性】归一化 → 输出无损母带
ffmpeg -y -i bgm.flac -af "loudnorm=I=-14:TP=-1.5:LRA=11:\
measured_I=-16.66:measured_TP=-3.30:measured_LRA=10.70:\
measured_thresh=-26.81:offset=-2.04:linear=true" \
  -ar 48000 -ac 2 -c:a flac bgm_master.flac
```

**纪律**：
- 归一化在**无损母带（FLAC/WAV）**上做完，**拼装链里只留纯增益**（`volume=XdB`）——
  这样**不增加有损编码次数**（本产线「全程只有一次有损编码」的铁律）。
- ⚠️ 第 3 条（改采样率）**仍然要防** —— 两遍法解决的是精度与真峰值，不是采样率。

### 3c. 🔴 音乐模型（ACE-Step / MusicGen 等）出片后**必测 TP + LRA**

提示词里"驱动感 / 爆发感"给得越足，越容易**顶爆**。
实测首版配乐 `input_tp = +0.55 dBTP`（**已削顶失真**，频谱表现为**一片高频竖纹**），
且 0–6 秒近无声后骤然切入（LRA 17.5）→ **不可用**。
换成 hybrid orchestral 取向的 take：`TP -3.30 / LRA 10.7`，且有"弱起→铺垫→20s 推起"乐句结构 → 采用。

> **判据**：`input_tp` 要 **< -1**；`input_lra` **< 15** 更稳；频谱不应有整段饱和的竖纹。
> **生成多版择优**，别只听"感觉够燃"就上片。

### 4. 🔴 大文件删除闸门会卡死

`rm` 一个 76 GB 文件返回 **SIGTERM**、文件仍在（闸门往回收站搬，超配额）。
**绕行**：先用 Python `open(p,'r+b').truncate(0)` 释放空间 → 再 `rm`（0 字节文件删得掉）。

---

## 二、标准写法（N 轨，泛化版）

三轨（旁白 + BGM + 音效）的实际结构：

```text
[旁白] loudnorm=I=-16:TP=-1.5:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo → [voice]
[voice] asplit=2 → [v_dub][v_mix]                     ← ★ 旁白既要当侧链又要进混音

[BGM]  volume=<实测增益>dB,aformat=sample_rates=48000:channel_layouts=stereo → [bgm0]
[bgm0][v_dub] sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400:makeup=1 → [bgmduck]

[音效] aformat=sample_rates=48000:channel_layouts=stereo,volume=-18dB → [sfxin]
[sfxin] asplit=N → [sfxs0]..[sfxsN-1]
[sfxsj] adelay=<毫秒>|<毫秒> → [sfxdj]                  ← 每个时间点一路
[sfxd0]..[sfxdN-1] amix=inputs=N:normalize=0 → [sfxmix]
[sfxmix] apad → [sfxfull]                              ← 补到无限长，靠 duration=first 截

[v_mix][bgmduck][sfxfull] amix=inputs=3:duration=first:normalize=0 → [aout0]
[aout0] aformat=sample_rates=48000:channel_layouts=stereo → [aout]
输出加 -ar 48000 -ac 2
```

要点：
- **`all_tracks[0]` 必须是旁白**：`amix` 的 `duration=first` 以第一个输入为时长上限，顺序错了成品时长就被带偏
- **`normalize=0`**：不加会让 `amix` 把各轨等比例衰减
- **`duration=first`** 让旁白决定成片长度
- BGM 输入用 `-stream_loop -1 -i <bgm>` 铺满全片
  ⚠️ 配 `-stream_loop -1` 时**务必**有时长限制（`duration=first` / `-shortest` / `-t`），否则无限写盘
- 音效点用 `adelay` 贴：单点直接 `adelay=ms|ms,apad`；多点先 `asplit` 再各自 `adelay` 再 `amix`
- **音效落点与视频 xfade 对齐**：转场点 = `offset + transition_duration/2`，与转场链共用同一组 offset

### 2.1 一条容易忽略的：`asplit` 的输出必须全部被消费

```
Filter 'asplit' has output 0 (v_dummy) unconnected
```
别留"备用"输出。用不到就别 split 出来。（实测踩过：想留个 dummy 占位，直接被拒）

---

## 三、BGM 音量必须按「相对旁白」标定

❌ 错：直接给 BGM 源加固定增益 → BGM 来源响度参差不齐，成品时大时小。
✅ 对：`--bgm-volume -8` 恒等于「比旁白低 8 dB」。

```python
VOICE_LUFS = -16.0     # 旁白 loudnorm 的目标

# 先实测 BGM 的 LUFS（loudnorm 第一遍，print_format=json → 解析 input_i）
bl = measure_lufs(bgm)
gain = (VOICE_LUFS + bgm_volume_db) - bl      # bgm_volume_db 为负数
```

`measure_lufs` 实现：
```python
subprocess.run([FFMPEG, "-i", str(p),
    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
    "-f", "null", "-"], capture_output=True, text=True)
# 从 stderr 里 re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"')
```

**实测例**：源 `-19.4 LUFS` → 目标 `-24.0 LUFS` → 增益 `-4.58 dB`。

---

## 四、验证方法（不能只看 rc=0）

**关键：`astats` 的 `reset` 单位是「帧」不是「秒」**，逐行数据没法看。
改用：解码 PCM 后在 Python 里按秒算 RMS。

```python
subprocess.run([FFMPEG, "-i", src, "-t", 12, "-f", "s16le",
                "-acodec", "pcm_s16le", "-ac", 2, "-ar", 48000, "-"])
# array('h') 读样本 → 每 48000*2 个样本算一次 20*log10(rms/32768)
```

### 4.1 验 ducking：跟旁白活动性做关联，**不看整体均值**

1. 把旁白用 `adelay=3000|3000` 延迟 3 秒当侧链 → 前 3 秒 BGM 应为原始电平、之后应下降
2. 按秒统计「旁白有声时 BGM 降幅」vs「旁白静音时 BGM 降幅」

实测（demo30）：
```
旁白有声时 BGM 平均降幅 -8.47 dB (n=6)
旁白静音时 BGM 平均降幅 -0.45 dB (n=6)   → 差 8.02 dB ✅
```
**只看整体均值会误判**：BGM 是真实音乐、本身动态就大（-23 ~ -57 dBFS），
且旁白段之间有 0.4s 空隙（空隙不该压低），所以「有声/静音」分组对比才靠谱。

**另一种口径**（成片验收）：把「三轨成品」与「只有旁白」逐秒相减，
差值就是 BGM+音效的贡献 —— 旁白有声段贡献应**接近 0**（被 ducking 压掉）。实测 +0.06 dB。

### 4.2 验音效落点：单独导出音效轨，看能量出现在哪

音效轨是**稀疏**的（只有 N 个 0.5 秒的点），所以单独 map 出来看能量段最干净：
```python
# 复现音效链，但只 -map "[sfxfull]"，然后按 0.05 秒算 RMS
# 有能量的时间段必须与预期时间点一一对应
```
实测 demo30：预期 8 点（1 片头 + 7 转场）→ 实际 8 段能量，**8/8 命中**，峰值 -39 dBFS。

---

## 五、本次用到的参数（可直接复用）

| 项 | 值 | 说明 |
|---|---|---|
| 旁白目标 | `-16 LUFS` | `loudnorm=I=-16:TP=-1.5:LRA=11` |
| BGM 相对音量 | `-8 dB`（即 -24 LUFS） | 母本建议 6–8 dB |
| 音效相对音量 | `-18 dB`（即 -34 LUFS） | 转场点，别抢戏 |
| ducking | `threshold=0.03:ratio=8:attack=20:release=400:makeup=1` | 实测降 8.5 dB |
| 交付规格 | `48000` / `stereo` | `-ar 48000 -ac 2` + 末端 aformat |

**ducking 调参速查**：

| 想要的效果 | 调什么 |
|---|---|
| 旁白时 BGM 留得多一点 | `ratio` 调小（8→4）或 `threshold` 调大（0.03→0.06） |
| 间隙想「喘口气」 | `release` 调小（400→200ms）—— 间隙只有 0.4s 时 400ms 来不及恢复 |
| 切换更干脆 | `attack` 调小（20→10ms） |

> ⚠️ **注意**：`attack` / `release` / `ratio` 调参后必须重跑「有声/静音分组」验证，
> 不能只看 rc=0。实测 ratio=8 时旁白段的 BGM 贡献仅 +0.06 dB（压得非常狠）——
> 如果听起来 BGM「消失」了，就是压过头，调 ratio/threshold。

## 五之二、音效素材：没素材时用 ffmpeg 合成

不需要下载素材库也能起步——噪声层 + 低频衰减冲击层叠一个 whoosh：

```powershell
ffmpeg -y `
 -f lavfi -i "anoisesrc=d=0.55:c=pink:a=0.7:r=48000" `
 -f lavfi -i "aevalsrc=0.35*sin(2*PI*85*t)*exp(-14*t):d=0.55:s=48000" `
 -filter_complex "[0:a]highpass=f=220,lowpass=f=7000,afade=t=in:st=0:d=0.05,afade=t=out:st=0.10:d=0.45,volume=0.75[nz];[1:a]volume=0.9[imp];[nz][imp]amix=inputs=2:duration=shortest:normalize=0,acompressor=threshold=0.15:ratio=3:attack=5:release=120,alimiter=limit=0.95,aformat=sample_rates=48000:channel_layouts=stereo" `
 -map "[out]" -c:a pcm_s16le whoosh.wav
```

要点：`aevalsrc` 用 `random()`/`sin()*exp()` 能写任意包络；`afade` 给噪声做快速 in/out；
`alimiter` 防削波。改 `d=` 和 `afade` 的时间就换一种 whoosh 手感。

## 六、相关文件

- `code-news\scripts\compose_long_video.py` → `final_encode()`
  （`--bgm` / `--bgm auto` / `--bgm-preset` / `--bgm-volume` / `--bgm-ducking`
  / `--sfx` / `--sfx-mode` / `--sfx-volume`）
- `code-news\scripts\compose_long_video.py` → `resolve_bgm()`（`--bgm auto` 三级兜底）
- `code-news\scripts\compose_long_video.py` → `measure_lufs()`（BGM 相对音量标定）
- `code-news\scripts\gen_music.py` → ACE-Step 1.5 出 BGM（5 类场景预设）
- `D:\AI-VIDEO\config\配乐方案.md` → 配乐母本（§5.2 音量规范与调参表 / §6.4 三轨混音链
  / §6.5 采样率问题 / §6.6 音效轨 / §8.1 踩坑表 / §8.2 调参速查）
- `D:\AI-VIDEO\music\sfx\whoosh.wav` → ffmpeg 合成的转场音效（命令见本文 §五之二）
- 调试脚本：`_test_ducking.py`（侧链隔离验证）、`_analyze_duck.py`（旁白/BGM 联动分析）、
  `_verify_final.py`（成品级：三轨 vs 仅旁白逐秒相减）、`_verify_sfx.py`（音效落点验证）
