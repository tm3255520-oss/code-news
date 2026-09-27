#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nvidia_model_audit.py — NVIDIA 免费模型目录巡检（自动化）

职责（确定性脚本，不走 LLM）：
  1. 拉取 NVIDIA /v1/models 全量目录（默认用 Windows 用户级 env NVIDIA_API_KEY）。
  2. 按母本 nvidia_adopt_rules 分类（adoptable / excluded / unknown）。
  3. 与母本 nvidia_curated 比对：
       OK       → 不动
       REPLACED → 同族新 ID（旧 ID + 日期后缀，唯一匹配）自动替换
       DELISTED → 无唯一替代自动清理（母本 + 工作副本 + codex catalog）
       NEW      → 命中采用家族自动登记进母本（媒体模型只登记，不进 codex）
  4. 自动同步：母本（vault）→ config/model_providers.json → Codex models.json → Hermes config.yaml 字符串替换。
5. 备份 + 快照 + 周报（vault 系统中枢/运行小结/）。

用法：
  python scripts/nvidia_model_audit.py --check      # 只读：拉目录+分类+比对，不写任何文件
  python scripts/nvidia_model_audit.py --keys       # 只读：NVIDIA key 指纹盘点（不出明文）
  python scripts/nvidia_model_audit.py --apply      # 自动执行：更新母本/工作副本/codex/hermes + 快照 + 周报
  python scripts/nvidia_model_audit.py --weekly     # = --apply（供 cron 每周一调用）
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

try:
    from nvidia_key_events import aggregate as aggregate_events
except Exception:
    def aggregate_events(*_a, **_k):  # type: ignore
        return {}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
VAULT_MASTER = Path(r"D:/Obsidian Vault/obsidian Vault/系统中枢/规则与权限/智能体共享/模型配置母本.md")
WORK_JSON = ROOT / "config" / "model_providers.json"
CODEX_CATALOG = Path(r"C:/Users/Administrator/.codex/models.json")
HERMES_CONFIG = Path(r"C:/Users/Administrator/.hermes/config.yaml")
HERMES_ENV = Path(r"C:/Users/Administrator/.hermes/.env")
KEY_REGISTRY = Path(r"D:/Obsidian Vault/obsidian Vault/系统中枢/各Agent档案/hermes/hermes相关 key汇总.md")
REPORT_DIR = Path(r"D:/Obsidian Vault/obsidian Vault/系统中枢/运行小结")
SNAPSHOT_DIR = ROOT / "data"
SNAPSHOT = SNAPSHOT_DIR / "nvidia_models_snapshot.json"
EVENT_LOG = SNAPSHOT_DIR / "nvidia_key_events.jsonl"
NVIDIA_LIST_URL = "https://integrate.api.nvidia.com/v1/models"


# ---------- 小工具 ----------

def mask(v: str, keep: int = 6) -> str:
    if not v or len(v) <= keep + 4:
        return "<empty>" if not v else v[:keep] + "…"
    return v[:keep] + "…" + v[-4:]


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    b = path.with_name(path.name + f".bak-nvidia-{ts}")
    shutil.copy2(path, b)
    return b


def load_master() -> tuple[dict, str]:
    raw = VAULT_MASTER.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if not m:
        raise RuntimeError("母本 frontmatter 解析失败")
    data = yaml.safe_load(m.group(1))
    body = raw[m.end():]
    return data, body


def save_master(data: dict, body: str) -> None:
    front = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                           default_flow_style=False, width=160)
    VAULT_MASTER.write_text("---\n" + front + "---\n" + body, encoding="utf-8")


def nvidia_key() -> str:
    k = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY_KIMI")
    if not k:
        import winreg
        try:
            hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
            for name in ("NVIDIA_API_KEY", "NVIDIA_API_KEY_KIMI"):
                try:
                    k, _ = winreg.QueryValueEx(hk, name)
                    if k:
                        break
                except OSError:
                    continue
        except OSError:
            pass
    if not k:
        raise RuntimeError("未找到 NVIDIA key（Windows env 或 NVIDIA_API_KEY 环境变量）")
    return k


def fetch_catalog(key: str) -> list[str]:
    req = urllib.request.Request(NVIDIA_LIST_URL, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    items = data.get("data") or []
    return [it.get("id") for it in items if it.get("id")]


# ---------- 分类 ----------

def classify(model_id: str, rules: dict) -> str:
    """返回 type 或 'excluded' 或 'unknown'。"""
    excluded = rules.get("excluded_patterns", [])
    if isinstance(excluded, str):
        excluded = [excluded]
    if any(re.search(p, model_id, re.I) for p in excluded):
        return "excluded"
    families = rules.get("families", {}) or {}
    for pat, mtype in families.items():
        if re.search(pat, model_id, re.I):
            return mtype
    return "unknown"


def find_replacement(old: str, catalog: list[str]) -> str | None:
    """旧 ID + '-' + 纯日期后缀，在目录里唯一匹配 → 返回新 ID。"""
    pat = re.compile(r"^" + re.escape(old) + r"-(\d{4})$")
    cands = [m for m in catalog if pat.match(m)]
    if len(cands) == 1:
        return cands[0]
    return None


def diff_curated(curated: dict, catalog: list[str], rules: dict) -> dict:
    curated_ids = set(curated.keys())
    catalog_set = set(catalog)
    ok = sorted(curated_ids & catalog_set)
    missing = sorted(curated_ids - catalog_set)
    replaced: dict[str, str] = {}
    delisted: list[str] = []
    for old in missing:
        new = find_replacement(old, catalog)
        if new:
            replaced[old] = new
        else:
            delisted.append(old)
    new_ids = sorted((catalog_set - curated_ids) - set(replaced.values()))
    adopted: dict[str, str] = {}      # id -> type
    unknown: list[str] = []
    excluded_new: list[str] = []
    for mid in new_ids:
        t = classify(mid, rules)
        if t in ("unknown", "excluded"):
            (unknown if t == "unknown" else excluded_new).append(mid)
        else:
            adopted[mid] = t
    return {
        "ok": ok,
        "replaced": replaced,
        "delisted": delisted,
        "adopted": adopted,
        "unknown": unknown,
        "excluded_new": excluded_new,
        "catalog_count": len(catalog),
    }


# ---------- key 指纹盘点（只读） ----------

def _fp(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()[:16]


def collect_nvidia_keys() -> dict[str, list[tuple[str, str]]]:
    """返回 value_fp -> [(来源, 变量名)]。"""
    out: dict[str, list[tuple[str, str]]] = {}

    def add(src: str, name: str, val: str):
        if not val or not val.strip():
            return
        out.setdefault(_fp(val.strip()), []).append((src, name))

    import winreg
    try:
        hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(hk, i)
                i += 1
                if name.startswith("NVIDIA") or "NVIDIA" in name:
                    add("win-user", name, str(val))
            except OSError:
                break
    except OSError:
        pass
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and line.strip().startswith("NVIDIA"):
                name, _, val = line.partition("=")
                add("hermes-.env", name.strip(), val.strip())
    for p in (Path(r"\\wsl$\Ubuntu\home\ubuntu\.dsh\.env"),
              Path(r"\\wsl$\Ubuntu\home\ubuntu\.env")):
        try:
            if p.exists():
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if "=" in line and line.strip().startswith("NVIDIA"):
                        name, _, val = line.partition("=")
                        add("wsl", name.strip(), val.strip())
        except OSError:
            pass
    return out


def registry_account_fps() -> dict[str, list[str]]:
    """从 vault key 登记表提取 NVIDIA 各账号的 key 指纹。返回 account -> [fp]。"""
    if not KEY_REGISTRY.exists():
        return {}
    txt = KEY_REGISTRY.read_text(encoding="utf-8", errors="replace")
    out: dict[str, list[str]] = {}
    cur = None
    for line in txt.splitlines():
        m = re.search(r"###\s+(Nivida-b|nvidia-wan|nvidia-c|nvidia-d|nvidia)\b", line, re.I)
        if m:
            cur = m.group(1).lower()
            out.setdefault(cur, [])
            continue
        if cur and re.search(r"nvapi-[A-Za-z0-9_\-]+", line):
            for tok in re.findall(r"nvapi-[A-Za-z0-9_\-]+", line):
                out[cur].append(_fp(tok))
    return out


def run_keys() -> None:
    groups = collect_nvidia_keys()
    master, _ = load_master()
    accts = master.get("nvidia_accounts", {})
    name_acct: dict[str, str] = {}
    for acct, info in accts.items():
        for item in info.get("keys", []):
            name_acct[item.get("env")] = acct
    print("=" * 70)
    print("NVIDIA key 指纹盘点（只读，未写任何文件）")
    print("=" * 70)
    rows = []
    for fp, sources in sorted(groups.items(), key=lambda kv: kv[0]):
        names = ", ".join(f"{s}:{n}" for s, n in sources)
        acct_hit = sorted({name_acct.get(n, "未归属") for _, n in sources})
        dup = len(sources) > 1
        rows.append((names, fp, acct_hit, dup))
    print(f"共 {len(rows)} 把不同 key（按指纹去重）\n")
    for names, fp, acct_hit, dup in rows:
        print(f"  fp={fp}  账号={','.join(acct_hit)}  重复引用={'YES' if dup else 'no'}")
        print(f"       {names}")
    print("\n=== 同名不同值（同一变量名多指纹）===")
    by_name: dict[str, set[str]] = {}
    for fp, sources in groups.items():
        for src, name in sources:
            by_name.setdefault(f"{src}:{name}", set()).add(fp)
    for name, fps in sorted(by_name.items()):
        if len(fps) > 1:
            print(f"  {name} -> {len(fps)} 个不同指纹")
    print("\n=== Windows 用户级 NVIDIA* 空值残留 ===")
    import winreg
    empty = []
    try:
        hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(hk, i)
                i += 1
                if "NVIDIA" in name and not str(val).strip():
                    empty.append(name)
            except OSError:
                break
    except OSError:
        pass
    print("  " + (", ".join(empty) if empty else "无"))
    print("\n注意：vault key 登记表与 .env 存在值脱节（部分槽位已轮换/过期），归属以母本 nvidia_accounts 命名为准。")


# ---------- 应用变更 ----------

def apply_changes(force: bool) -> dict:
    if not force:
        raise RuntimeError("internal: apply requires force")
    key = nvidia_key()
    catalog = fetch_catalog(key)
    master, body = load_master()
    rules = master.setdefault("nvidia_adopt_rules", {})
    curated = master.setdefault("nvidia_curated", {})
    if not curated:
        # 首次：从 providers.nvidia.models 生成 curated 骨架
        for mid in (master.get("providers", {}).get("nvidia", {}).get("models", {}) or {}):
            curated.setdefault(mid, {"type": "text_chat", "fallback": "", "account": "nvidia(待核对)", "used_by": []})
    diff = diff_curated(curated, catalog, rules)

    print(f"目录共 {diff['catalog_count']} 个模型")
    print(f"OK={len(diff['ok'])}  REPLACED={len(diff['replaced'])}  DELISTED={len(diff['delisted'])}  "
          f"NEW-采用={len(diff['adopted'])}  unknown={len(diff['unknown'])}  excluded={len(diff['excluded_new'])}")

    # 1) 更新母本 curated（保留原 roles）
    old_models = (master.get("providers", {}).get("nvidia", {}).get("models", {}) or {})
    new_curated: dict = {}
    for mid in diff["ok"]:
        entry = copy.deepcopy(curated.get(mid, {"type": "text_chat", "fallback": "", "account": "nvidia(待核对)", "used_by": []}))
        entry.setdefault("roles", old_models.get(mid, {}).get("roles", ["general"]))
        new_curated[mid] = entry
    for old, new in diff["replaced"].items():
        entry = copy.deepcopy(curated.get(old, {"type": "text_chat", "fallback": "", "account": "nvidia(待核对)", "used_by": []}))
        entry["fallback"] = old
        entry.setdefault("roles", old_models.get(old, {}).get("roles", ["general"]))
        new_curated[new] = entry
        print(f"  [REPLACED] {old} -> {new}")
    for mid in diff["delisted"]:
        print(f"  [DELISTED] {mid}（已清理；hermes 路由若有引用将自愈，详见周报）")
    for mid, mtype in diff["adopted"].items():
        new_curated[mid] = {"type": mtype, "fallback": "", "account": "待分配", "used_by": []}
        print(f"  [ADOPTED] {mid} (type={mtype})")
    master["nvidia_curated"] = dict(sorted(new_curated.items()))

    # 2) 更新母本 providers.nvidia.models（镜像 curated）
    nv_models = {}
    for mid, entry in master["nvidia_curated"].items():
        nv_models[mid] = {"roles": entry.get("roles") or old_models.get(mid, {}).get("roles", ["general"])}
    master["providers"]["nvidia"]["models"] = nv_models
    save_master(master, body)
    print("  [master] 母本已更新")

    # 3) 镜像到工作副本 config/model_providers.json
    if WORK_JSON.exists():
        backup(WORK_JSON)
        wj = json.loads(WORK_JSON.read_text(encoding="utf-8"))
        wj["providers"]["nvidia"]["models"] = copy.deepcopy(nv_models)
        WORK_JSON.write_text(json.dumps(wj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("  [work-json] config/model_providers.json 已同步")

    # 4) Codex models.json：替换/清理 nvidia 条目；新增 text 类
    if CODEX_CATALOG.exists():
        backup(CODEX_CATALOG)
        cat = json.loads(CODEX_CATALOG.read_text(encoding="utf-8", errors="replace"))
        mods = cat["models"]
        removed = []
        for i, m in enumerate(mods):
            slug = m.get("slug", "")
            if slug in diff["replaced"]:
                m["slug"] = diff["replaced"][slug]
                m["display_name"] = diff["replaced"][slug].split("/")[-1]
            elif slug in diff["delisted"]:
                removed.append(slug)
        mods = [m for m in mods if m.get("slug") not in set(removed)]
        existing = {m.get("slug") for m in mods}
        template = next((m for m in mods if m.get("slug") == "deepseek-ai/deepseek-v4-pro-0813"), None)
        for mid, mtype in diff["adopted"].items():
            if mtype not in ("text_chat", "code"):
                continue
            if mid in existing:
                continue
            if template:
                ne = copy.deepcopy(template)
                ne["slug"] = mid
                ne["display_name"] = mid.split("/")[-1]
                ne["context_window"] = 262144
                ne["max_context_window"] = 262144
                ne["priority"] = 30
                mods.append(ne)
                existing.add(mid)
        cat["models"] = mods
        CODEX_CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  [codex] models.json 已同步（移除 {len(removed)}，新增文本 {sum(1 for m in diff['adopted'] if m in existing)}）")

    # 5) Hermes config.yaml：仅 REPLACED 做精确字符串替换（DELISTED 留待自愈，周报标注）
    if HERMES_CONFIG.exists() and diff["replaced"]:
        backup(HERMES_CONFIG)
        hc = HERMES_CONFIG.read_text(encoding="utf-8", errors="replace")
        for old, new in diff["replaced"].items():
            pat = re.compile(r"(?<![A-Za-z0-9\-])" + re.escape(old) + r"(?![A-Za-z0-9\-])")
            hc, n = pat.subn(new, hc)
            print(f"  [hermes] {old} -> {new}（替换 {n} 处）")
        HERMES_CONFIG.write_text(hc, encoding="utf-8")

    # 6) 快照
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "catalog_count": diff["catalog_count"],
        "catalog": catalog,
        "diff": {k: v for k, v in diff.items() if k != "catalog_count"},
    }
    SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  [snapshot] data/nvidia_models_snapshot.json 已写")

    # 7) 周报
    write_report(diff)
    return diff


def write_report(diff: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    p = REPORT_DIR / f"{today}-nvidia模型巡检.md"
    L = []
    L.append("---")
    L.append(f"title: NVIDIA 模型巡检 {today}")
    L.append("tags: [nvidia, 模型巡检, 自动化]")
    L.append("---")
    L.append("")
    L.append(f"# NVIDIA 模型巡检（{today}）")
    L.append("")
    L.append(f"- 目录模型总数：**{diff['catalog_count']}**")
    L.append(f"- 正常：{len(diff['ok'])}　已替换：{len(diff['replaced'])}　已清理：{len(diff['delisted'])}　"
             f"新采用：{len(diff['adopted'])}　未知：{len(diff['unknown'])}　排除：{len(diff['excluded_new'])}")
    L.append("")
    if diff["replaced"]:
        L.append("## 自动替换（REPLACED）")
        L.append("")
        for old, new in diff["replaced"].items():
            L.append(f"- `{old}` → `{new}`")
        L.append("")
    if diff["delisted"]:
        L.append("## 自动清理（DELISTED，无唯一同族替代）")
        L.append("")
        for mid in diff["delisted"]:
            L.append(f"- `{mid}`（已从母本/工作副本/Codex catalog 移除；Hermes 路由引用将自愈）")
        L.append("")
    if diff["adopted"]:
        L.append("## 自动采用（NEW，命中采用家族）")
        L.append("")
        L.append("| 模型 | 类型 |")
        L.append("|---|---|")
        for mid, t in diff["adopted"].items():
            L.append(f"| `{mid}` | {t} |")
        L.append("")
    if diff["unknown"]:
        L.append("## 未知类型候选（不自动采用，待归入规则表）")
        L.append("")
        for mid in diff["unknown"][:30]:
            L.append(f"- `{mid}`")
        L.append("")
    if diff["excluded_new"]:
        L.append("## 排除（科研/行业类，不采用）")
        L.append("")
        L.append(f"共 {len(diff['excluded_new'])} 个，示例：" + "、".join(f"`{m}`" for m in diff["excluded_new"][:10]))
        L.append("")
    L.append("## Key 健康（每日 10:00 探活，13 把 key）")
    L.append("")
    health = read_key_health()
    acct_map = account_name_map()
    if not health:
        L.append("（暂无探活状态文件；每日 watch_nvidia_keys.py 首次运行后生成。）")
    else:
        L.append("| key | 账号 | 状态 |")
        L.append("|---|---|---|")
        for var, status in health.items():
            L.append(f"| `{var}` | {acct_map.get(var, '未归属')} | {status} |")
        ok = sum(1 for s in health.values() if s == "200")
        L.append("")
        L.append(f"可用：{ok}/{len(health)}　（403=账号级回收等自愈 1-7 天，勿动配置；429=模型限流可换模型）")
        L.append("")
    L.append("## 负载汇总（近期 403/429 事件）")
    L.append("")
    agg = aggregate_events()
    if not agg:
        L.append("（暂无事件记录；埋点已接入 Codex NVIDIA 代理，遇到 403/429 会自动写入。）")
    else:
        L.append("| 账号 | 模型 | 状态 | 次数 |")
        L.append("|---|---|---|---|")
        for acct, models in sorted(agg.items()):
            for model, stats in sorted(models.items()):
                for status, cnt in sorted(stats.items()):
                    L.append(f"| {acct} | `{model}` | {status} | {cnt} |")
        L.append("")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  [report] {p}")


def read_key_health() -> dict:
    """读每日探活状态文件（watch_nvidia_keys.py 写入）。"""
    sf = Path(r"C:/Users/Administrator/.hermes/cache/nvidia_key_watch.json")
    if not sf.exists():
        return {}
    try:
        return json.loads(sf.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def account_name_map() -> dict:
    """env 变量名 → 账号（来自母本 nvidia_accounts）。"""
    out: dict = {}
    try:
        master, _ = load_master()
        for acct, info in (master.get("nvidia_accounts") or {}).items():
            for item in info.get("keys", []):
                out[item.get("env")] = acct
    except Exception:
        pass
    return out


def run_check() -> None:
    key = nvidia_key()
    print(f"使用 key：{mask(key)}")
    catalog = fetch_catalog(key)
    master, _ = load_master()
    rules = master.get("nvidia_adopt_rules", {})
    curated = master.get("nvidia_curated", {})
    if not curated:
        curated = {m: {"type": "text_chat"} for m in (master.get("providers", {}).get("nvidia", {}).get("models", {}) or {})}
    diff = diff_curated(curated, catalog, rules)
    print(f"目录共 {diff['catalog_count']} 个模型")
    print(f"OK({len(diff['ok'])}): " + ", ".join(diff["ok"]))
    if diff["replaced"]:
        print("REPLACED: " + "; ".join(f"{o}->{n}" for o, n in diff["replaced"].items()))
    if diff["delisted"]:
        print("DELISTED: " + ", ".join(diff["delisted"]))
    if diff["adopted"]:
        print("ADOPTED: " + "; ".join(f"{m}({t})" for m, t in diff["adopted"].items()))
    if diff["unknown"]:
        print(f"UNKNOWN({len(diff['unknown'])}): " + ", ".join(diff["unknown"][:20]) + (" …" if len(diff["unknown"]) > 20 else ""))
    if diff["excluded_new"]:
        print(f"EXCLUDED({len(diff['excluded_new'])}): " + ", ".join(diff["excluded_new"][:12]))


def main() -> None:
    ap = argparse.ArgumentParser(description="NVIDIA 模型目录巡检")
    ap.add_argument("--check", action="store_true", help="只读检查")
    ap.add_argument("--keys", action="store_true", help="NVIDIA key 指纹盘点（只读）")
    ap.add_argument("--apply", action="store_true", help="自动应用变更")
    ap.add_argument("--weekly", action="store_true", help="= --apply")
    args = ap.parse_args()
    if args.keys:
        run_keys()
    elif args.check or args.apply or args.weekly:
        if args.apply or args.weekly:
            apply_changes(force=True)
        else:
            run_check()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
