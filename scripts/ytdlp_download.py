#!/usr/bin/env python3
"""ytdlp_download.py - yt-dlp 下载的**抗抖动**统一入口（确定性，无 LLM）。

背景（2026-09-30 实测，lab probe-002 ~ probe-006）
--------------------------------------------------
1) yt-dlp 本身没坏。缺的是 JS 运行时：不加 `--js-runtimes node:<path>` 会报
   "No supported JavaScript runtime could be found" 与
   "n challenge solving failed: Some formats may be missing"。
   补上之后，真实 YouTube 视频下载 rc=0、stderr 全空（probe-005 的 G）。
   （不需要 `--remote-components ejs:github` —— node 单独就够，避免从 GitHub 拉第三方脚本。）
   该 flag 已写进全局 `%APPDATA%\\yt-dlp\\config.txt`，本模块再显式带一份做双保险。

   **写 config 文件的坑**：yt-dlp 解析配置文件时会**吃掉反斜杠**——
   `node:C:\\Users\\Administrator\\...` 会被静默读成 `node:C:UsersAdministrator...`，
   路径失效、JS 运行时注册不上，而且只在 `--verbose` 的 "User config" 那行才看得见。
   所以配置文件里的路径**必须用正斜杠**（`node:C:/Users/...`）。实测见 lab probe-008。

2) 真正的坑在**网络路径**。本机经代理访问 YouTube，长传输会在约 45 秒 / 约 28MB 处**冻结**：
   连接被半关，既不报错也不触发 socket 超时；yt-dlp 就那么干等（probe-004 冻 6 分钟零字节，
   probe-005 复现；stderr 常伴 "unable to extract yt initial data"）。
   `--retries / --fragment-retries / --socket-timeout` 都拉不回来。

3) 治法是**看门狗 + 断点续传**：盯着输出目录体积，停滞超过 `stall_s` 就杀掉重跑；
   已下部分以 `.part` 保留，重跑用 `--continue` 字节级续传。
   实测一支 10 分钟视频分 2 段下完（34.45MB，rc=0）——probe-006。

   **不能只看体积**：下载完两条分流后，yt-dlp 要调 ffmpeg **合并**，而合并不涨字节——
   单纯"停滞即杀"会把正在合并的健康进程杀掉，永远等不到成品（踩过，probe-009）。
   所以停滞杀进程的前提是目录里**仍有 `.part`**（=确实还在下载）。

与「单步失败不重试」铁律的关系
------------------------------
本模块重试的是**同一个传输的续传**（幂等、字节级接续），不是"重试失败的步骤"，
也不引入任何 LLM 判断。调用方仍应按原有约定在彻底失败时标记 failed 并继续下一步。

用法
----
    from ytdlp_download import robust_download
    r = robust_download(url, os.path.join(out_dir, "video.mp4"))
    if r["ok"]:
        video_path = r["path"]        # 实际产物（可能是 .mp4/.webm/.mkv）
    else:
        ...                            # r["error"] 里有最后一段 stderr

命令行自测：
    python scripts/ytdlp_download.py <url> <out_path> [--fmt FMT]
"""
import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 本机 node（yt-dlp 用做 JS 运行时解 n 挑战）
_NODE_CANDIDATES = [
    r"C:\Users\Administrator\.hermes\node\node.exe",
]

_MEDIA_EXT = (".mp4", ".webm", ".mkv", ".mov", ".flv", ".m4a", ".mp3", ".wav")
_STALL_S = 30      # 体积停滞多久判"冻死"（仅当仍有 .part 在下载时才据此杀进程）
_WALL_S = 150      # 单次最长
_ATTEMPTS = 6      # 最多续几次（实测本机每段净下 ~30MB，720p 十分钟片约 78MB → 需 3~4 段）


def find_node():
    """找一个可用的 node（用于 --js-runtimes）。找不到返回 None（yt-dlp 会退化为无 JS 运行时）。"""
    for p in _NODE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return shutil.which("node")


def _dir_bytes(d):
    tot = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                tot += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return tot


def _has_part(d):
    """目录里是否还有 .part（= 仍有分流文件在下载中）。"""
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith(".part"):
                return True
    return False


def _find_output(out_dir, stem):
    """在目录里找已完成的产物（排除 .part 与 yt-dlp 的分流中间文件 stem.fNNN.ext）。"""
    ext_re = r"\.(" + "|".join(e.lstrip(".") for e in _MEDIA_EXT) + r")$"
    for name in sorted(os.listdir(out_dir)):
        if not name.startswith(stem + "."):
            continue
        if name.endswith(".part"):
            continue
        if re.match(r"^" + re.escape(stem) + r"\.f\d+\.", name):
            continue
        if not re.search(ext_re, name, re.I):
            continue
        p = os.path.join(out_dir, name)
        try:
            if os.path.getsize(p) > 0:
                return p
        except OSError:
            pass
    return None


def _build_cmd(url, out_path, fmt, merge, extra, node):
    cmd = [sys.executable, "-m", "yt_dlp", "--newline", "--no-playlist", "--continue"]
    if node:
        cmd += ["--js-runtimes", "node:" + node]
    cmd += ["--socket-timeout", "15", "--retries", "10",
            "--fragment-retries", "10", "--retry-sleep", "3"]
    cmd += ["-f", fmt]
    if merge:
        cmd += ["--merge-output-format", merge]
    cmd += ["-o", out_path]
    if extra:
        cmd += list(extra)
    cmd += ["--", url]
    return cmd


def robust_download(url, out_path, fmt="bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/bv*+ba/b", merge=None,
                    stall_s=_STALL_S, wall_s=_WALL_S, attempts=_ATTEMPTS,
                    extra=None, log=print):
    """下载 url 到 out_path；停滞自动杀掉并续传。

    返回 dict: {ok, path, attempts, size_MB, tries:[...], error}
    - ok=True 时 path 为实际产物（可能与 out_path 扩展名不同，如合并成 .webm）。
    - 幂等：out_path（或同 stem 的产物）已存在且非空 → 立即返回 ok。
    """
    out_path = os.path.abspath(out_path)
    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(out_path))[0]
    # 关键：-o 必须给**模板**（stem.%(ext)s），不能给带扩展名的具体文件名。
    # 否则 yt-dlp 把 "video.mp4" 当模板基名，分流文件变成 "video.mp4.f398.mp4"（纯视频轨），
    # 会被误判为"已完成"——实测踩过（probe-008）。
    template = os.path.join(out_dir, stem + ".%(ext)s")

    # 幂等：已有产物直接返回
    pre = _find_output(out_dir, stem)
    if pre:
        return {"ok": True, "path": pre, "attempts": 0, "size_MB": round(os.path.getsize(pre) / 1048576, 2),
                "tries": [], "error": "", "note": "已存在，跳过"}

    # 目标要 .mp4 → 让 yt-dlp 直接合成 mp4（配合默认 fmt 里的 ext=mp4/m4a 约束，
    # YouTube 一定给得出来，避免合成成 .webm 害下游按 video.mp4 找不到）
    if merge is None and out_path.lower().endswith(".mp4"):
        merge = "mp4"

    node = find_node()
    cmd = _build_cmd(url, template, fmt, merge, extra, node)
    if not node:
        log("[ytdlp] 未找到 node，n 挑战可能解不了（高质量档会被跳过）", "WARN")
    else:
        log(f"[ytdlp] JS 运行时: {node}", "INFO")

    tries = []
    err = ""
    for i in range(1, attempts + 1):
        t0 = time.time()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace",
                                stdin=subprocess.DEVNULL, cwd=out_dir)
        last_b, last_t = _dir_bytes(out_dir), t0
        killed = False
        while proc.poll() is None:
            time.sleep(5)
            b = _dir_bytes(out_dir)
            if b > last_b:
                last_b, last_t = b, time.time()
            stalled = (time.time() - last_t) > stall_s
            # 只在"仍有 .part 在下载"时才因停滞杀进程；
            # 没有 .part 说明分流已下完、正在合并/后处理（合并不涨字节，别误杀）。
            if (time.time() - t0 > wall_s) or (stalled and _has_part(out_dir)):
                killed = True
                try:
                    proc.kill()
                except Exception:
                    pass
                break
        _out, err = proc.communicate()

        found = _find_output(out_dir, stem)
        rec = {"attempt": i, "rc": proc.returncode, "killed": killed,
               "secs": round(time.time() - t0, 1),
               "dir_MB": round(_dir_bytes(out_dir) / 1048576, 2),
               "got_MB": round(os.path.getsize(found) / 1048576, 2) if found else 0}
        tries.append(rec)

        if found:
            log(f"[ytdlp] 第 {i} 段结束：产物 {os.path.basename(found)} "
                f"{rec['got_MB']}MB（{'已续传完成' if i > 1 else '一次成功'}）", "INFO")
            return {"ok": True, "path": found, "attempts": i, "size_MB": rec["got_MB"],
                    "tries": tries, "error": ""}

        log(f"[ytdlp] 第 {i} 段结束：未完成 rc={proc.returncode} "
            f"{'（停滞被杀，续传）' if killed else '（退出）'} {rec['secs']}s "
            f"已下 {rec['dir_MB']}MB", "WARN")

    return {"ok": False, "path": "", "attempts": attempts, "size_MB": 0,
            "tries": tries, "error": (err or "").strip()[-400:]}


def main():
    ap = argparse.ArgumentParser(description="yt-dlp 抗抖动下载（看门狗 + 断点续传）")
    ap.add_argument("url")
    ap.add_argument("out_path")
    ap.add_argument("--fmt", default="bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/bv*+ba/b")
    ap.add_argument("--merge", default=None)
    a = ap.parse_args()
    r = robust_download(a.url, a.out_path, fmt=a.fmt, merge=a.merge)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
