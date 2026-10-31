#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
provider_model_audit.py — 全供应商模型目录巡检（自动化）

覆盖供应商（有 /models 目录接口）：
  nvidia  / bailian(阿里百炼) / deepseek / minimax / kimi
Agnes / HermesOne 无目录接口 → 母本静态登记，不自动拉取。

职责（确定性脚本，不走 LLM）：
  1. 拉取各供应商模型目录。
  2. 按母本 <provider>_adopt_rules 分类（text/code/vision/image/video/audio/…）。
  3. 与母本 <provider>_curated 比对：OK / REPLACED / DELISTED / NEW。
  4. 自动替换（同族新 ID）、清理（无替代）、采用（命中家族）；媒体模型按类型登记。
  5. 同步母本 + config/model_providers.json；nvidia 额外同步 Codex models.json，并把
     「下架且无同族替代」的死 pin 换成在架同角色模型（Hermes config.yaml、cron jobs.json、
     脚本 LLM_MODEL 默认值）——定时任务因此自动改用其他模型。
  6. 快照 + 周报（含 Key 健康、负载汇总、媒体短清单）。

用法：
  python scripts/provider_model_audit.py --check    # 只读
  python scripts/provider_model_audit.py --apply    # 自动执行
  python scripts/provider_model_audit.py --weekly   # = --apply（供 cron）
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

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
KEY_WATCH = Path(r"C:/Users/Administrator/.hermes/cache/nvidia_key_watch.json")
CRON_JOBS = Path(r"C:/Users/Administrator/.hermes/cron/jobs.json")
REPORT_DIR = Path(r"D:/Obsidian Vault/obsidian Vault/系统中枢/运行小结")
SNAPSHOT_DIR = ROOT / "data"
SNAPSHOT = SNAPSHOT_DIR / "provider_models_snapshot.json"

try:
    from nvidia_key_events import aggregate as aggregate_events
except Exception:
    def aggregate_events(*_a, **_k):  # type: ignore
        return {}

PROVIDER_SPECS = [
    {"id": "nvidia", "catalog": "https://integrate.api.nvidia.com/v1/models", "key_env": "NVIDIA_API_KEY",
     "rules_key": "nvidia_adopt_rules", "curated_key": "nvidia_curated",
     "models_path": ["providers", "nvidia", "models"], "codex": True, "hermes": True},
    {"id": "bailian", "catalog": "https://dashscope.aliyuncs.com/compatible-mode/v1/models", "key_env": "BAILIAN_API_KEY",
     "rules_key": "bailian_adopt_rules", "curated_key": "bailian_curated",
     "models_path": ["providers", "bailian", "models"]},
    {"id": "deepseek", "catalog": "https://api.deepseek.com/models", "key_env": "DEEPSEEK_API_KEY",
     "rules_key": "deepseek_adopt_rules", "curated_key": "deepseek_curated",
     "models_path": ["providers", "deepseek", "models"]},
    {"id": "minimax", "catalog": "https://api.minimaxi.com/v1/models", "key_env": "MINIMAX_API_KEY",
     "rules_key": "minimax_adopt_rules", "curated_key": "minimax_curated",
     "models_path": ["providers", "minimax", "models"]},
    {"id": "kimi", "catalog": "https://api.moonshot.cn/v1/models", "key_env": "KIMI_CN_API_KEY",
     "rules_key": "kimi_adopt_rules", "curated_key": "kimi_curated",
     "models_path": ["providers", "kimi", "models"]},
]


# ---------- 基础工具 ----------

def mask(v: str, keep: int = 6) -> str:
    if not v:
        return "<empty>"
    return v[:keep] + "…" + v[-4:] if len(v) > keep + 4 else v[:keep] + "…"


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    b = path.with_name(path.name + f".bak-provider-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, b)
    return b


def load_master() -> tuple[dict, str]:
    raw = VAULT_MASTER.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if not m:
        raise RuntimeError("母本 frontmatter 解析失败")
    return yaml.safe_load(m.group(1)), raw[m.end():]


def save_master(data: dict, body: str) -> None:
    front = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                           default_flow_style=False, width=160)
    VAULT_MASTER.write_text("---\n" + front + "---\n" + body, encoding="utf-8")


# ---------- 写入前完整性守卫（2026-09-15 新增） ----------

REQUIRED_PROVIDER_FIELDS = ("key_env", "endpoints")


def check_config_integrity(doc: dict, label: str) -> list[str]:
    """检查 providers 段的「连接字段」是否完整，返回问题清单（空=通过）。

    为什么需要这道守卫（2026-09-14 根因取证结论）：
      本脚本是 model_providers.json 的**唯一自动写入方**，但 apply_provider()
      只管理 providers.<id>.models 子树 —— 它既不校验、也不补回 provider 级的
      key_env 与 endpoints。于是配置一旦丢字段，**每跑一次都把它原样固化，
      永不自愈**。

      真实事故：配置在 2026-09-05 16:30 从 23KB 掉到 1094B（5 个 provider 的
      key_env / endpoints 全部丢失），此后 9/6、9/7、9/11 三轮巡检都原样保留，
      无人察觉；叠加 9/9 NVIDIA 老模型整批 EOL（HTTP 410），最终导致视频号
      产线**连续 5 天断供**，且排查成本极高（根因藏在两个故障的叠加处）。

      守卫的目的：把「缺字段」从**静默通过**变成**响亮的失败**。

    判据（最小且准确）：每个 provider 必须同时具备非空的 key_env 与 endpoints。
      - key_env 登记密钥的**环境变量名**（绝不落明文）
      - endpoints 提供各 wire 的基址；缺了 gateway/resolve 就取不到端点

    豁免：若某 provider 确实无需连接字段（如纯静态登记项），请显式加
      `"static": true`，本守卫会跳过它。
    """
    problems: list[str] = []
    provs = doc.get("providers")
    if not isinstance(provs, dict) or not provs:
        problems.append(f"{label}: providers 段为空或缺失")
        return problems
    for pid, cfg in provs.items():
        if not isinstance(cfg, dict):
            problems.append(f"{label}: providers.{pid} 不是对象（{type(cfg).__name__}）")
            continue
        if cfg.get("static"):
            continue  # 显式豁免：静态登记项
        for field in REQUIRED_PROVIDER_FIELDS:
            if not cfg.get(field):
                problems.append(f"{label}: providers.{pid} 缺 {field}")
    return problems


def report_guard_failure(problems: list[str]) -> None:
    """打印守卫失败详情与处置指引（走 stderr，确保 cron 日志里醒目）。"""
    print("\n" + "=" * 68, file=sys.stderr)
    print("🛑 [GUARD] 配置完整性校验未通过 —— 已拒绝写入，避免固化损坏状态",
          file=sys.stderr)
    print("=" * 68, file=sys.stderr)
    for p in problems:
        print(f"    - {p}", file=sys.stderr)
    print("-" * 68, file=sys.stderr)
    print(" 处置：", file=sys.stderr)
    print("   1) 从最近一次健康备份取回缺失字段：", file=sys.stderr)
    print(f"      {WORK_JSON}.bak-provider-*（挑体积明显更大的那个）", file=sys.stderr)
    print("   2) key_env 只写**环境变量名**，endpoints 补齐各 wire 基址；", file=sys.stderr)
    print("   3) 确认 `python scripts/model_gateway.py` 能解析出 key 后重跑本脚本。", file=sys.stderr)
    print(" 注：本次未写入任何文件，磁盘配置保持原样。", file=sys.stderr)
    print("=" * 68, file=sys.stderr)


def resolve_key(env_name: str) -> str | None:
    v = os.environ.get(env_name)
    if v:
        return v
    try:
        import winreg
        hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        try:
            v, _ = winreg.QueryValueEx(hk, env_name)
            if v:
                return str(v)
        except OSError:
            pass
    except OSError:
        pass
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(env_name + "="):
                return line.partition("=")[2].strip()
    return None


def fetch_catalog(url: str, key: str) -> list[str]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    items = data.get("data") or data.get("models") or []
    ids = []
    for it in items:
        if isinstance(it, dict):
            mid = it.get("id") or it.get("name")
            if mid:
                ids.append(str(mid))
    return ids


def classify(model_id: str, rules: dict) -> str:
    excluded = rules.get("excluded_patterns", []) or []
    if isinstance(excluded, str):
        excluded = [excluded]
    if any(re.search(p, model_id, re.I) for p in excluded):
        return "excluded"
    for pat, mtype in (rules.get("families", {}) or {}).items():
        if re.search(pat, model_id, re.I):
            return mtype
    for pat in (rules.get("candidate_families", []) or []):
        if re.search(pat, model_id, re.I):
            return "candidate"
    return "unknown"


def find_replacement(old: str, catalog: list[str]) -> str | None:
    pat = re.compile(r"^" + re.escape(old) + r"-(\d{4})$")
    cands = [m for m in catalog if pat.match(m)]
    return cands[0] if len(cands) == 1 else None


def diff_curated(curated: dict, catalog: list[str], rules: dict) -> dict:
    curated_ids = set(curated.keys())
    catalog_set = set(catalog)
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
    adopted: dict[str, str] = {}
    unknown: list[str] = []
    candidates: list[str] = []
    excluded_new: list[str] = []
    for mid in new_ids:
        t = classify(mid, rules)
        if t == "candidate":
            candidates.append(mid)
        elif t == "unknown":
            unknown.append(mid)
        elif t == "excluded":
            excluded_new.append(mid)
        else:
            adopted[mid] = t
    return {"ok": sorted(curated_ids & catalog_set), "replaced": replaced,
            "delisted": delisted, "adopted": adopted, "unknown": unknown, "candidates": candidates,
            "excluded_new": excluded_new, "catalog_count": len(catalog)}


def get_by_path(d: dict, path: list[str]) -> dict:
    cur = d
    for k in path:
        cur = cur.setdefault(k, {})
    return cur


# ---------- 应用 ----------

def apply_provider(master: dict, spec: dict, catalog: list[str], work_json: dict, changed: dict) -> None:
    rules = master.get(spec["rules_key"], {})
    curated = master.setdefault(spec["curated_key"], {})
    models_map = get_by_path(master, spec["models_path"])
    if not curated:
        for mid in (models_map or {}):
            curated.setdefault(mid, {"type": "text_chat", "fallback": "", "used_by": []})
    diff = diff_curated(curated, catalog, rules)
    old_models = dict(models_map or {})
    new_curated: dict = {}
    for mid in diff["ok"]:
        entry = copy.deepcopy(curated.get(mid, {"type": "text_chat", "fallback": "", "used_by": []}))
        entry.setdefault("roles", old_models.get(mid, {}).get("roles", ["general"]))
        new_curated[mid] = entry
    for old, new in diff["replaced"].items():
        entry = copy.deepcopy(curated.get(old, {"type": "text_chat", "fallback": "", "used_by": []}))
        entry["fallback"] = old
        entry.setdefault("roles", old_models.get(old, {}).get("roles", ["general"]))
        new_curated[new] = entry
    kept_static: list[str] = []
    for mid in diff["delisted"]:
        entry = curated.get(mid, {})
        if entry.get("static"):
            new_curated[mid] = copy.deepcopy(entry)  # static：目录外模型（如 ai.api.nvidia.com flux）保留
            kept_static.append(mid)
    diff["delisted_static"] = kept_static
    for mid, mtype in diff["adopted"].items():
        new_curated[mid] = {"type": mtype, "fallback": "", "used_by": []}
    master[spec["curated_key"]] = dict(sorted(new_curated.items()))
    new_models: dict = {}
    for mid, e in master[spec["curated_key"]].items():
        entry = {"roles": e.get("roles") or old_models.get(mid, {}).get("roles", ["general"])}
        if e.get("key_env"):
            entry["key_env"] = e["key_env"]
        new_models[mid] = entry
    models_map.clear()
    models_map.update(new_models)
    # 同步工作副本
    wj_models = get_by_path(work_json, spec["models_path"])
    wj_models.clear()
    wj_models.update(copy.deepcopy(new_models))
    if spec.get("codex") and spec.get("hermes"):
        # 下架/替换 → 在架替代：供 sync_nvidia_extras 替换 cron/脚本/config 里的死引用。
        # 视图要合并新旧 curated：旧条目提供下架模型的 roles，新条目（含本次 adopted）
        # 提供候选的 type —— 否则刚上架的同族继任接不上（实测漏过 deepseek-v4.1-flash）。
        view = {**curated, **new_curated}
        diff["remap"] = build_remap(diff, view, master.get("nvidia_pin_preference") or [],
                                    probe=probe_model_callable)
    changed[spec["id"]] = diff
    print(f"[{spec['id']}] 目录={diff['catalog_count']} OK={len(diff['ok'])} "
          f"REPLACED={len(diff['replaced'])} DELISTED={len(diff['delisted']) - len(kept_static)} "
          f"(static保留={len(kept_static)}) "
          f"ADOPTED={len(diff['adopted'])} candidate={len(diff.get('candidates', []))} "
          f"unknown={len(diff['unknown'])} excluded={len(diff['excluded_new'])}")
    for old, new in diff["replaced"].items():
        print(f"    [REPLACED] {old} -> {new}")
    for mid in diff["delisted"]:
        if mid in kept_static:
            print(f"    [STATIC-KEEP] {mid}")
        else:
            print(f"    [DELISTED] {mid}")
    for mid, t in diff["adopted"].items():
        print(f"    [ADOPTED] {mid} ({t})")



def _family_key(model_id: str) -> tuple[str, str]:
    """返回 (vendor, 家族首 token)，如 deepseek-ai/deepseek-v4-flash-0731 -> ('deepseek-ai','deepseek')。

    只认 -YYYY 日期后缀会漏掉「改名继任」（deepseek-v4-flash-0731 → deepseek-v4.1-flash），
    同族判定用于把这类新模型接上旧 pin。
    """
    vendor, _, name = model_id.partition("/")
    token = re.split(r"[-_.]", name)[0] if name else ""
    return vendor.lower(), token.lower()


def choose_pin_fallback(dead: str, live: list[str], curated: dict,
                        preference: list[str], probe=None) -> str | None:
    """为下架模型选一个当前在架的替代（确定性排序 + 可选可调用性实测）。

    排序 tier：偏好表内且同族 > 偏好表内 > 同族 > 其他；同 tier 按偏好序、再按字母序。
    偏好表（母本 nvidia_pin_preference）是手工维护的「实测可用」短名单 —— 只按目录
    同族挑会挑到「目录在架、账号实际调不通」的模型（实测 nvidia/llama-3.1-nemotron-51b-instruct
    目录在架却整片 404）。

    probe 传入时，按序实测候选是否真能调通（返回 True），避免把死 pin 换成一个同样调不通的 pin。
    """
    cands = [m for m in live if (curated.get(m) or {}).get("type") in ("text_chat", "code")]
    if not cands:
        cands = sorted(live)
    if not cands:
        return None
    roles = set((curated.get(dead) or {}).get("roles") or [])
    if roles:
        same_role = [m for m in cands if roles & set((curated.get(m) or {}).get("roles") or [])]
        if same_role:
            cands = same_role
    fam = _family_key(dead)

    def rank(m: str) -> tuple:
        pref = preference.index(m) if m in preference else len(preference)
        same = _family_key(m) == fam
        tier = 0 if (same and m in preference) else 1 if m in preference else 2 if same else 3
        return (tier, pref, m)

    ranked = sorted(cands, key=rank)
    if probe:
        for cand in ranked[:3]:
            if probe(cand):
                return cand
    return ranked[0]


_CALLABLE_CACHE: dict[str, bool] = {}


def probe_model_callable(model: str, timeout: int = 15) -> bool:
    """用主 key 实测一次最小对话，判断模型是否真的能调通（结果进程内缓存）。

    目录在架 ≠ 能调用：部分目录模型的账号权限是分级/回收状态（实测 404/403）。
    返回 False 不代表模型永久不可用，只表示这一次实测没通。
    """
    if model in _CALLABLE_CACHE:
        return _CALLABLE_CACHE[model]
    ok = False
    key = resolve_key("NVIDIA_API_KEY")
    if key:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "好"}],
                           "max_tokens": 5}).encode("utf-8")
        req = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ok = int(getattr(resp, "status", 200)) == 200
        except Exception:
            ok = False
    _CALLABLE_CACHE[model] = ok
    return ok


def build_remap(diff: dict, curated_before: dict, preference: list[str],
                probe=None) -> dict[str, str]:
    """「下架/替换 → 在架替代」完整映射（static 保留项不参与）。"""
    live = list(diff.get("ok") or []) + list((diff.get("adopted") or {}).keys())
    remap = dict(diff.get("replaced") or {})
    static = set(diff.get("delisted_static") or [])
    for dead in diff.get("delisted") or []:
        if dead in static or (curated_before.get(dead) or {}).get("static"):
            continue
        fb = choose_pin_fallback(dead, live, curated_before, preference, probe)
        if fb:
            remap[dead] = fb
    return remap


_ID_RE = r"[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*"
_MARKED_ID = re.compile(r"(?:model|default_model|primary|slug)['\"]?\s*:\s*['\"]?(" + _ID_RE + r")", re.I)
_KEY_ID = re.compile(r"^\s*(" + _ID_RE + r")\s*:\s*$")


def model_ids_in_line(line: str) -> set[str]:
    """取一行里处于「模型位置」的 id：model/default_model/primary/slug 的值，或 models 映射的键。

    只认位置、不做全文匹配，是为了不把日志路径（logs/hermes.log）、端口（8750/v1）、
    prompt 里的普通文字（「nvidia/bailian/deepseek/minimax/kimi 拉目录」）当成模型。
    """
    out = {m.group(1) for m in _MARKED_ID.finditer(line)}
    m = _KEY_ID.match(line)
    if m:
        out.add(m.group(1))
    return out


def _dead_models(ids: set[str], catalog: list[str]) -> set[str]:
    vendors = {i.split("/")[0].lower() for i in catalog}
    cat = set(catalog)
    return {m for m in ids if m.split("/")[0].lower() in vendors and m not in cat}


def find_catalog_orphans(text: str, catalog: list[str]) -> set[str]:
    """配置里引用、但英伟达目录已无此 id 的模型（含从未进 curated 的僵尸引用）。"""
    return _dead_models({m for line in text.splitlines() for m in model_ids_in_line(line)}, catalog)


def find_config_orphans(text: str, catalog: list[str]) -> set[str]:
    """Hermes config.yaml 专用：在 find_catalog_orphans 基础上，排除走非目录端点的 provider 块。

    例：nvidia_paligemma 走 http://127.0.0.1:8750/v1 本地代理，其 google/paligemma
    不在英伟达目录里，但属于正常配置 —— 替换会弄坏 OCR 通道。
    """
    keep: set[str] = set()
    drop: set[str] = set()
    local_block = False
    for line in text.splitlines():
        if line.strip() and (not line.startswith(" ") or
                             (re.match(r"^  \S", line) and not line.startswith("   "))):
            local_block = False
        if re.match(r"^\s+base_url:", line):
            url = line.split("base_url:", 1)[1].strip().strip("'\"")
            local_block = "integrate.api.nvidia.com" not in url
        dead = _dead_models(model_ids_in_line(line), catalog)
        (drop if local_block else keep).update(dead)
    return keep - drop


def replace_model_ids(text: str, mapping: dict[str, str]) -> tuple[str, list[tuple[str, str, int]]]:
    """按 id 长度降序做边界安全替换，返回 (新文本, [(旧, 新, 次数)])。

    边界必须排除 . - _ ：nvidia/...-49b-v1 是 nvidia/...-49b-v1.5 的前缀，
    只排除 [A-Za-z0-9-] 会把 v1.5 改坏成 <新 id>.5。
    """
    hits: list[tuple[str, str, int]] = []
    for old in sorted(mapping, key=len, reverse=True):
        pat = re.compile(r"(?<![A-Za-z0-9\-._])" + re.escape(old) + r"(?![A-Za-z0-9\-._])")
        text, n = pat.subn(mapping[old], text)
        if n:
            hits.append((old, mapping[old], n))
    return text, hits


def drop_duplicate_yaml_keys(text: str, targets: set[str]) -> tuple[str, int]:
    """删掉同一父块内重复的同名模型键（保留第一处），返回 (新文本, 删除数)。

    批量替换会把两个不同的死 id 映射到同一个替代模型，于是同一个 models: 映射里
    出现两个同名键：PyYAML 静默取后者（会把 name 覆盖成旧模型的），严格解析器还会报错。

    两条安全约束：
      • 只对 targets（本次替换的目标模型 id）生效，其它键一律不动；
      • 序列项（- 开头）是独立作用域，不会跨项被误判成同名兄弟
        （早期版本漏了这条，把 smart_model_routing 的 3 条策略删成 1 条）。
    """
    if not targets:
        return text, 0
    lines = text.split("\n")
    out: list[str] = []
    stack: list[tuple[int, int]] = []                  # (缩进, out 下标) 已打开的作用域
    seen_at: dict[tuple[int, int], set] = {}           # (父作用域下标, 缩进) -> 已见键
    dropped = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        body = line.lstrip(" ")
        indent = len(line) - len(body)
        if not body or body.startswith("#"):
            out.append(line)
            i += 1
            continue
        if body == "-" or body.startswith("- "):
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, len(out)))
            out.append(line)
            i += 1
            continue
        m = re.match(r"^([^\s#][^:]*):\s*$", body)
        if not m:
            out.append(line)
            i += 1
            continue
        key = m.group(1)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if key in targets:
            parent = stack[-1][1] if stack else -1
            seen = seen_at.setdefault((parent, indent), set())
            if key in seen:
                dropped += 1
                i += 1
                while i < len(lines):                  # 连子行一起丢弃
                    nbody = lines[i].strip()
                    nindent = len(lines[i]) - len(lines[i].lstrip(" "))
                    if nbody and nindent <= indent:
                        break
                    i += 1
                continue
            seen.add(key)
        stack.append((indent, len(out)))
        out.append(line)
        i += 1
    return "\n".join(out), dropped


def sync_runtime_pins(mapping: dict[str, str]) -> None:
    """脚本里的 LLM_MODEL 默认值：死 pin → 在架替代。"""
    if not mapping:
        return
    import glob as _glob
    roots = [r"C:/Users/Administrator/.hermes/scripts",
             r"C:/Users/Administrator/Documents/code-news/scripts"]
    pat_llm = re.compile(r'(os\.environ\.get\("LLM_MODEL",\s*")([^"]+)(")')
    for root in roots:
        for f in _glob.glob(root + "/**/*.py", recursive=True):
            if "__pycache__" in f:
                continue
            try:
                txt = open(f, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            hit = [mm for mm in pat_llm.findall(txt) if mm[1] in mapping]
            if not hit:
                continue
            backup(Path(f))
            txt2 = pat_llm.sub(
                lambda m: m.group(1) + mapping[m.group(2)] + m.group(3)
                if m.group(2) in mapping else m.group(0), txt)
            Path(f).write_text(txt2, encoding="utf-8")
            for old in sorted({h[1] for h in hit}):
                print(f"    [runtime-pin] {Path(f).name}: {old} -> {mapping[old]}")


def sync_text_refs(mapping: dict[str, str]) -> None:
    """Hermes config.yaml + cron jobs.json：死模型 id 替换为在架替代。

    用文本级替换（不解析重写），以保留 config.yaml 的注释与 jobs.json 的原始格式。
    """
    if not mapping:
        return
    for label, path in (("hermes", HERMES_CONFIG), ("cron-jobs", CRON_JOBS)):
        if not path.exists():
            continue
        txt = path.read_text(encoding="utf-8", errors="replace")
        new_txt, hits = replace_model_ids(txt, mapping)
        if not hits:
            continue
        if path.suffix in (".yaml", ".yml"):
            new_txt, dupes = drop_duplicate_yaml_keys(new_txt, set(mapping.values()))
            if dupes:
                print(f"    [{label}] 替换后清理重复映射键 {dupes} 处")
        backup(path)
        path.write_text(new_txt, encoding="utf-8")
        for old, new, n in hits:
            print(f"    [{label}] {old} -> {new}（{n} 处）")


def sync_nvidia_extras(master: dict, diff: dict, catalog: list[str]) -> None:
    """nvidia 专属：把下架/替换的模型在配置、cron 任务、脚本、Codex 目录里的引用一并换掉。"""
    remap = dict(diff.get("remap") or {})
    live = list(diff.get("ok") or []) + list((diff.get("adopted") or {}).keys())
    curated = master.get("nvidia_curated") or {}
    pref = master.get("nvidia_pin_preference") or []
    protected = set(curated) | set(remap)   # curated 里的（含 static 保留）已由上面处理
    for path, scanner in ((HERMES_CONFIG, find_config_orphans),
                          (CODEX_CATALOG, find_catalog_orphans),
                          (CRON_JOBS, find_catalog_orphans)):
        if not path.exists():
            continue
        orphans = scanner(path.read_text(encoding="utf-8", errors="replace"), catalog)
        for orphan in sorted(orphans - protected):
            fb = choose_pin_fallback(orphan, live, curated, pref, probe_model_callable)
            if fb:
                remap[orphan] = fb
                print(f"    [orphan] {orphan} -> {fb}")
    diff["remap"] = remap
    if not remap and not diff.get("adopted"):
        return

    if CODEX_CATALOG.exists():
        cat = json.loads(CODEX_CATALOG.read_text(encoding="utf-8", errors="replace"))
        mods = cat["models"]
        for m in mods:
            old_slug = m.get("slug")
            if old_slug in remap:
                m["slug"] = remap[old_slug]
                m["display_name"] = m["slug"].split("/")[-1]
        delisted = set(diff.get("delisted") or [])
        kept, seen = [], set()
        dropped = []
        for m in mods:
            slug = m.get("slug", "")
            if slug in seen or (slug in delisted and slug not in remap):
                dropped.append(slug)
                continue
            seen.add(slug)
            kept.append(m)
        template = next((m for m in kept if m.get("slug") in set(live)), None) \
            or next((m for m in kept if "/" in m.get("slug", "")), None)
        added = 0
        for mid, mtype in (diff.get("adopted") or {}).items():
            if mtype not in ("text_chat", "code") or mid in seen or not template:
                continue
            ne = copy.deepcopy(template)
            ne["slug"] = mid
            ne["display_name"] = mid.split("/")[-1]
            ne["context_window"] = 262144
            ne["max_context_window"] = 262144
            ne["priority"] = 30
            kept.append(ne)
            seen.add(mid)
            added += 1
        cat["models"] = kept
        backup(CODEX_CATALOG)
        CODEX_CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"    [codex] models.json 已同步（死引用替换 {len(remap)}，移除 {len(dropped)}，新增 {added}）")
    sync_text_refs(remap)
    sync_runtime_pins(remap)


def read_key_health() -> dict:
    if not KEY_WATCH.exists():
        return {}
    try:
        return json.loads(KEY_WATCH.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def account_name_map() -> dict:
    out: dict = {}
    try:
        master, _ = load_master()
        for acct, info in (master.get("nvidia_accounts") or {}).items():
            for item in info.get("keys", []):
                out[item.get("env")] = acct
    except Exception:
        pass
    return out


def write_report(changed: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    p = REPORT_DIR / f"{today}-供应商模型巡检.md"
    L = ["---", f"title: 供应商模型巡检 {today}", "tags: [模型巡检, 自动化, 供应商]", "---", "",
         f"# 供应商模型巡检（{today}）", ""]
    for pid, d in changed.items():
        L.append(f"## {pid}（目录 {d['catalog_count']}）")
        L.append(f"- OK={len(d['ok'])}　替换={len(d['replaced'])}　清理={len(d['delisted'])}　"
                 f"采用={len(d['adopted'])}　unknown={len(d['unknown'])}　排除={len(d['excluded_new'])}")
        if d["replaced"]:
            L.append("")
            for old, new in d["replaced"].items():
                L.append(f"- `{old}` → `{new}`")
        delisted = [m for m in d.get("delisted", []) if m not in set(d.get("delisted_static", []))]
        if d.get("delisted_static"):
            L.append("")
            for mid in d["delisted_static"]:
                L.append(f"- 静态保留（目录外，巡检不清理）`{mid}`")
        if delisted:
            L.append("")
            for mid in delisted:
                L.append(f"- 清理 `{mid}`")
        if d.get("remap"):
            L.append("")
            L.append("死引用替换（下架/替换 → 在架替代，已同步 Hermes 配置 / cron 任务 / 脚本 pin）：")
            L.append("")
            for old, new in sorted(d["remap"].items()):
                L.append(f"- `{old}` → `{new}`")
        if d["adopted"]:
            L.append("")
            L.append("| 模型 | 类型 |")
            L.append("|---|---|")
            for mid, t in d["adopted"].items():
                L.append(f"| `{mid}` | {t} |")
        cands = d.get("candidates", [])
        if cands:
            L.append("")
            L.append(f"文本候选（不自动采用，需人工/精选确认，{len(cands)}）：" +
                     "、".join(f"`{m}`" for m in cands[:12]))
        if d["unknown"]:
            L.append("")
            L.append(f"unknown（{len(d['unknown'])}）：" + "、".join(f"`{m}`" for m in d["unknown"][:12]))
        L.append("")
    L.append("## Key 健康（NVIDIA 每日探活）")
    L.append("")
    health = read_key_health()
    acct_map = account_name_map()
    if not health:
        L.append("（暂无探活状态文件）")
    else:
        L.append("| key | 账号 | 状态 |")
        L.append("|---|---|---|")
        for var, status in health.items():
            L.append(f"| `{var}` | {acct_map.get(var, '未归属')} | {status} |")
        ok = sum(1 for s in health.values() if s == "200")
        L.append("")
        L.append(f"可用：{ok}/{len(health)}")
        L.append("")
    L.append("## 负载汇总（近期 403/429 事件）")
    L.append("")
    agg = aggregate_events()
    if not agg:
        L.append("（暂无事件记录）")
    else:
        L.append("| 账号 | 模型 | 状态 | 次数 |")
        L.append("|---|---|---|---|")
        for acct, models in sorted(agg.items()):
            for model, stats in sorted(models.items()):
                for status, cnt in sorted(stats.items()):
                    L.append(f"| {acct} | `{model}` | {status} | {cnt} |")
        L.append("")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[report] {p}")


def run_apply() -> int:
    backup(VAULT_MASTER)
    if WORK_JSON.exists():
        backup(WORK_JSON)
    master, body = load_master()
    work_json = json.loads(WORK_JSON.read_text(encoding="utf-8")) if WORK_JSON.exists() else {"providers": {}}
    changed: dict = {}
    for spec in PROVIDER_SPECS:
        key = resolve_key(spec["key_env"])
        if not key:
            print(f"[{spec['id']}] 无 key，跳过")
            continue
        try:
            catalog = fetch_catalog(spec["catalog"], key)
        except Exception as e:
            print(f"[{spec['id']}] 拉取失败：{e}")
            continue
        apply_provider(master, spec, catalog, work_json, changed)
        if spec.get("codex") and spec.get("hermes"):
            sync_nvidia_extras(master, changed[spec["id"]], catalog)

    # ---- 写入前完整性守卫（2026-09-15 新增）----
    # 放在此处而非函数开头：此时内存里的 master / work_json 已跑完全部 provider
    # 处理，检查的就是**即将落盘的内容**。apply_provider 只动 models 子树，
    # 因此若输入已损坏，这里必然拦下（而不是把残废态再固化一轮）。
    problems = (check_config_integrity(master, "模型配置母本")
                + check_config_integrity(work_json, "model_providers.json"))
    if problems:
        report_guard_failure(problems)
        return 1

    print("[guard] 配置完整性校验通过：providers 连接字段齐全")
    save_master(master, body)
    if WORK_JSON.exists():
        WORK_JSON.write_text(json.dumps(work_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap = {"date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "providers": {pid: {k: v for k, v in d.items()} for pid, d in changed.items()}}
    SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[snapshot] {SNAPSHOT}")
    write_report(changed)
    print("[done] 全供应商巡检完成")
    return 0


def run_check() -> None:
    master, _ = load_master()
    for spec in PROVIDER_SPECS:
        key = resolve_key(spec["key_env"])
        if not key:
            print(f"[{spec['id']}] 无 key，跳过")
            continue
        try:
            catalog = fetch_catalog(spec["catalog"], key)
        except Exception as e:
            print(f"[{spec['id']}] 拉取失败：{e}")
            continue
        curated = master.get(spec["curated_key"], {})
        if not curated:
            curated = {m: {"type": "text_chat"} for m in (get_by_path(master, spec["models_path"]) or {})}
        d = diff_curated(curated, catalog, master.get(spec["rules_key"], {}))
        print(f"[{spec['id']}] 目录={d['catalog_count']} 精选={len(curated)} "
              f"OK={len(d['ok'])} REPLACED={len(d['replaced'])} DELISTED={len(d['delisted'])} "
              f"ADOPTED={len(d['adopted'])} unknown={len(d['unknown'])}")


def main() -> None:
    ap = argparse.ArgumentParser(description="全供应商模型目录巡检")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--weekly", action="store_true")
    args = ap.parse_args()
    if args.check or args.apply or args.weekly:
        rc = (run_apply if (args.apply or args.weekly) else run_check)()
        # 守卫拦截时返回非零 → 让 cron / 包装脚本能感知这次没写成功（2026-09-15）
        if rc:
            sys.exit(rc)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
