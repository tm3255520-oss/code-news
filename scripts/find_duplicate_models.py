#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_duplicate_models.py —— 模型库重复副本检测与硬链接化

为什么需要这个工具（2026-10-20 实战得出的四条纪律）：

1. **找重复必须算 SHA256，不能只比体积。**
   实测 15 个 SD1.5 controlnet 都是 0.67 GB，但哈希全不同 —— 它们是 13 个不同模型。
   只比体积会把它们误判成重复。

2. **必须先查 ReparsePoint（符号链接 / 硬链接 / junction）。**
   实测 `ComfyUI\\models\\audio_vae` 是指向 `AI-VIDEO\\models\\audio_vae` 的符号链接。
   跟着链接统计会把同一份数据算两遍 → 误判成"两份拷贝"。

3. **处置用硬链接，而不是删除。**
   删掉副本就少一条路径，只要还有代码/配置指向它，功能就断。
   硬链接让两条路径指向同一份数据：磁盘只占一份，路径都还在，随时可反向拆开。

4. **停摆 ≠ 废弃。** 本工具只报重复，不判断模型"有没有用" —— 那是业务判断，不归它管。

用法（默认只读，--apply 才动手）：

    # 1) 只检测、只报告
    python scripts/find_duplicate_models.py --roots "D:/AI-VIDEO/models" "D:/AI-VIDEO/ComfyUI/models"

    # 2) 检测并把重复副本改成硬链接（不删任何路径）
    python scripts/find_duplicate_models.py --roots "D:/AI-VIDEO/models" ... --apply --record out.json

    # 3) 反向拆开（把硬链接恢复成独立副本）
    python scripts/find_duplicate_models.py --rollback record.json

安全性：
- 默认 dry-run；--apply 才会改文件系统
- 改的是「副本 → 硬链接」，**不删任何路径**；数据始终由保留份持有
- 每组改完立即校验 inode + sha256，失败自动回滚
- --record 落 JSON，供 --rollback 使用
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
from typing import Dict, Iterable, List, Tuple

REPARSE_POINT = 0x400
CHUNK = 8 * 1024 * 1024
DEFAULT_MIN_MB = 50


# ── 基础工具 ────────────────────────────────────────────────────────────
def is_reparse_point(path: str) -> bool:
    """Windows 的符号链接 / junction / 其他重解析点。跟着它统计会把同一份数据算两遍。"""
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE_POINT)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def human(n: float) -> str:
    return f"{n / 2**30:.2f} GB"


# ── 扫描 ────────────────────────────────────────────────────────────────
def collect_files(roots: Iterable[str], min_bytes: int) -> Tuple[List[Tuple[str, int]], List[str]]:
    """返回 (候选大文件, 跳过的重解析点)。只收集普通文件。"""
    files: List[Tuple[str, int]] = []
    skipped_links: List[str] = []
    for root in roots:
        if not os.path.isdir(root):
            print(f"[跳过] 路径不存在：{root}", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            if is_reparse_point(dirpath):
                skipped_links.append(dirpath)
                dirnames[:] = []
                continue
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    st = os.stat(path, follow_symlinks=False)
                except OSError:
                    continue
                if getattr(st, "st_file_attributes", 0) & REPARSE_POINT:
                    skipped_links.append(path)
                    continue
                if st.st_size >= min_bytes:
                    files.append((path, st.st_size))
    return files, skipped_links


def find_duplicate_groups(
    files: List[Tuple[str, int]], progress: bool = True
) -> List[Dict]:
    """体积分组 → 同体积候选算 SHA256 → 内容一致者为重复组。"""
    by_size: Dict[int, List[str]] = collections.defaultdict(list)
    for path, size in files:
        by_size[size].append(path)
    candidates = {s: ps for s, ps in by_size.items() if len(ps) > 1}

    groups: List[Dict] = []
    total_hashed = 0
    for size, paths in candidates.items():
        by_hash: Dict[str, List[str]] = collections.defaultdict(list)
        for path in paths:
            try:
                by_hash[sha256_of(path)].append(path)
            except OSError as exc:
                print(f"[读失败] {path}：{exc}", file=sys.stderr)
            total_hashed += 1
        for digest, same in by_hash.items():
            if len(same) > 1:
                # 已经硬链接化的一组：内容相同、inode 也相同 → 磁盘上本来就只占一份，
                # **不能再算进「可回收」**（否则重复统计，把已回收的量再报一遍）。
                inodes = set()
                for path in same:
                    try:
                        inodes.add(os.stat(path).st_ino)
                    except OSError:
                        pass
                already_linked = len(inodes) == 1
                groups.append(
                    {
                        "size": size,
                        "sha256": digest,
                        "paths": sorted(same),
                        "already_linked": already_linked,
                        "reclaimable": 0 if already_linked else size * (len(same) - 1),
                    }
                )
    if progress:
        print(f"[哈希] 同体积候选文件 {total_hashed} 个已逐个算 SHA256", file=sys.stderr)
    return sorted(groups, key=lambda g: -g["reclaimable"])


# ── 硬链接化 ────────────────────────────────────────────────────────────
def hardlink_ify(group: Dict, keep: str, dry_run: bool = True) -> Dict:
    """把 group 里除 keep 之外的路径改成指向 keep 的硬链接。

    三步：① 建临时硬链接 → ② 删副本（keep 仍持数据） → ③ 原子替换回原路径。
    数据全程由 keep 持有，任一步失败可回滚；**不删任何路径**。
    """
    size = group["size"]
    digest = group["sha256"]
    results = []
    for dup in group["paths"]:
        if os.path.normcase(dup) == os.path.normcase(keep):
            continue
        if dry_run:
            results.append({"dup": dup, "status": "dry-run", "size": size})
            continue
        tmp = dup + ".hl_tmp"
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
            os.link(keep, tmp)                      # ① 建硬链接，不动原文件
            inode = os.stat(tmp).st_ino
            os.remove(dup)                           # ② 删副本（keep 持数据，不丢）
            os.replace(tmp, dup)                    # ③ 原子替换，路径恢复
            same_inode = os.stat(dup).st_ino == inode
            hash_ok = sha256_of(dup) == digest
            ok = same_inode and hash_ok and os.path.getsize(dup) == size
            results.append(
                {
                    "dup": dup,
                    "status": "ok" if ok else "verify-failed",
                    "inode": inode,
                    "same_inode": same_inode,
                    "hash_ok": hash_ok,
                    "size": size,
                }
            )
            if not ok:  # 校验不过立刻回滚：把副本从 keep 复制回来
                import shutil

                shutil.copy2(keep, dup)
                results[-1]["status"] = "rolled-back"
        except Exception as exc:  # noqa: BLE001 —— 任何异常都要保证路径还在
            if os.path.exists(tmp) and not os.path.exists(dup):
                os.replace(tmp, dup)
            results.append({"dup": dup, "status": f"error: {exc}", "size": size})
    return {"keep": keep, "sha256": digest, "size": size, "results": results}


def rollback(record_path: str) -> int:
    """把硬链接恢复成独立副本（唯一真正"多占一份"的状态）。"""
    record = json.load(open(record_path, encoding="utf-8"))
    done = 0
    for entry in record.get("groups", []):
        keep = entry["keep"]
        for res in entry.get("results", []):
            dup = res.get("dup")
            if not dup or res.get("status") != "ok":
                continue
            try:
                if os.path.exists(dup) and os.stat(dup).st_ino == os.stat(keep).st_ino:
                    import shutil

                    tmp = dup + ".rb_tmp"
                    shutil.copy2(keep, tmp)
                    os.replace(tmp, dup)
                    done += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[回滚失败] {dup}：{exc}", file=sys.stderr)
    print(f"[回滚] 已拆开 {done} 个硬链接")
    return 0


# ── 主流程 ──────────────────────────────────────────────────────────────
def pick_keep(group: Dict, prefer: List[str]) -> str:
    """选保留份：优先命中 --prefer 里的路径前缀，否则取排序后的第一个。

    内部自排序：group 可能来自 JSON（不保证 paths 有序），必须自己排。
    """
    paths = sorted(group["paths"])
    for pref in prefer:
        for path in paths:
            if path.startswith(pref):
                return path
    return paths[0]


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="模型库重复副本检测与硬链接化（默认只读）",
    )
    ap.add_argument("--roots", nargs="+", help="要扫描的根目录")
    ap.add_argument("--min-mb", type=int, default=DEFAULT_MIN_MB, help="小于该体积的文件不参与（默认 50MB）")
    ap.add_argument("--apply", action="store_true", help="真的把重复副本改成硬链接（默认只报告）")
    ap.add_argument("--prefer", nargs="*", default=[], help="保留份的路径前缀优先级")
    ap.add_argument("--record", help="硬链接化记录 JSON 落盘路径（供 --rollback 使用）")
    ap.add_argument("--json", help="检测结果 JSON 落盘路径")
    ap.add_argument("--rollback", help="按记录 JSON 反向拆开硬链接")
    args = ap.parse_args(argv)

    if args.rollback:
        return rollback(args.rollback)
    if not args.roots:
        ap.error("需要 --roots（或用 --rollback）")

    min_bytes = args.min_mb * 1024 * 1024
    files, skipped = collect_files(args.roots, min_bytes)
    total = sum(s for _, s in files)
    print(f"[扫描] {len(args.roots)} 个根目录，候选 {len(files)} 个文件 / {human(total)}")
    print(f"[扫描] 跳过重解析点（符号链接/junction）{len(skipped)} 个 —— 它们不是重复")

    groups = find_duplicate_groups(files)
    linked = [g for g in groups if g.get("already_linked")]
    pending = [g for g in groups if not g.get("already_linked")]
    reclaim = sum(g["reclaimable"] for g in pending)
    print(f"\n===== 内容完全相同（SHA256 一致）的重复组：{len(groups)} 组 =====")
    print(f"     其中已硬链接化（同 inode、磁盘只占一份）：{len(linked)} 组")
    print(f"     待处理（真拷贝，各占一份）：{len(pending)} 组，可回收 {human(reclaim)}\n")

    record_groups = []
    for g in groups:
        keep = pick_keep(g, args.prefer)
        if g.get("already_linked"):
            print(f"{human(g['size'])} × {len(g['paths'])} 份  sha256={g['sha256'][:16]}…  ✅ 已硬链接化（无可回收）")
            for p in g["paths"]:
                print(f"    同源: {p}")
            print()
            continue
        print(f"{human(g['size'])} × {len(g['paths'])} 份  sha256={g['sha256'][:16]}…  保留={keep}")
        for p in g["paths"]:
            if p != keep:
                print(f"    重复: {p}")
        outcome = hardlink_ify(g, keep, dry_run=not args.apply)
        record_groups.append({"keep": keep, "sha256": g["sha256"], "size": g["size"], "results": outcome["results"]})
        if args.apply:
            for r in outcome["results"]:
                if r.get("status") == "ok":
                    print(f"    [硬链接化] OK  inode={r['inode']}  {r['dup']}")
                elif r.get("status") not in ("dry-run",):
                    print(f"    [硬链接化] {r['status']}  {r['dup']}")
        print()

    if args.json:
        json.dump(
            {"groups": groups, "skipped_links": skipped, "reclaimable": reclaim},
            open(args.json, "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=1,
        )
        print(f"[记录] 检测结果 → {args.json}")
    if args.record:
        json.dump(
            {"groups": record_groups, "roots": args.roots},
            open(args.record, "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=1,
        )
        print(f"[记录] 硬链接化记录 → {args.record}（可用 --rollback 反向拆开）")

    if not args.apply:
        print("[提示] 以上为 dry-run；加 --apply 才会把重复副本改成硬链接（不删任何路径）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
