#!/usr/bin/env python3
"""供应商一致性守卫 —— 母本 / 扫描器 / 工作副本 / Agent 路由 四方对账 + 降级链落地校验。

立项背景（2026-10-06）：智谱、火山、千帆三家早有 key、代理也在跑，却一家都没进母本。
根因是「加一家供应商」要在 4~5 个地方手写登记，只登了一半，而且没有任何机制能发现漏登。
现有 check_config_integrity 只校验连接字段，抓不到「.env 有 key、母本没这家」这类反向缺失。

四个面对账（另加第五、六面：降级链落地校验 + role 默认模型落地校验）：
  (1) 母本 模型配置母本.md front-matter —— 单一登记点（客观层）
  (2) 扫描器 provider_model_audit.py 的 PROVIDER_SPECS / PROBE_PROVIDERS
  (3) 工作副本 config/model_providers.json
  (4) Agent 侧 .codex/config.toml 的 [model_providers.*] + codex_model_router.py 的 ROUTES
  (5) fallback_chains 的 provider/model 引用必须能落地到 providers[].models（§164 修法 D）
  (6) 每个 role 的最终解析模型必须能落地到某 provider（E11，与 resolve() 口径同构）

用法：
  python scripts/check_provider_consistency.py           # 人读报告
  python scripts/check_provider_consistency.py --quiet   # 只输出问题
退出码：0 = 无错误（可能带提示）；1 = 有错误（须修）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import provider_model_audit as AUDIT  # noqa: E402  同目录工具：复用母本解析与规格表
from model_gateway import ROLE_DEFAULTS  # noqa: E402  第6面：与 resolve() 的代码内置兜底同源

VAULT_MASTER = AUDIT.VAULT_MASTER
WORK_JSON = ROOT / "config" / "model_providers.json"
HERMES_ENV = Path.home() / ".hermes" / ".env"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"

# Agent 侧 provider id 与母本不同名时的别名（agent 侧 -> 母本 id）
PROVIDER_ALIAS = {"volc": "ark"}

# Agent 配置里引用的、但不属于任何供应商的 key（自用鉴权等）
ENV_REF_IGNORE = {"CODEX_ROUTER_KEY": "Codex 路由器自用鉴权，非供应商 key"}


def declared_key_envs(fm: dict) -> set:
    """母本里所有被声明过的 key 变量名（provider / 账号槽位 / media_configs 全算）。"""
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("key_env", "env") and isinstance(v, str):
                    out.add(v)
                elif k == "key_envs" and isinstance(v, list):
                    out.update(x for x in v if isinstance(x, str))
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(fm)
    return out


def env_provider_keys() -> list:
    if not HERMES_ENV.exists():
        return []
    keys = []
    for line in HERMES_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k = line.split("=", 1)[0].strip()
            if re.search(r"(_API_KEY|_KEY|_SECRET_KEY)$", k):
                keys.append(k)
    return sorted(set(keys))


def codex_provider_envs() -> dict:
    """解析 .codex/config.toml 的 [model_providers.<id>] env_key。"""
    if not CODEX_CONFIG.exists():
        return {}
    out = {}
    cur = None
    for line in CODEX_CONFIG.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        m = re.match(r"^\[model_providers\.([A-Za-z0-9_\-]+)\]$", s)
        if m:
            cur = m.group(1)
            continue
        if s.startswith("[") and not s.startswith("[model_providers."):
            cur = None
            continue
        if cur and s.startswith("env_key"):
            out[cur] = s.split("=", 1)[1].strip().strip('"').strip("'")
    return out


def router_routes() -> list:
    """codex_model_router.py 的 (前缀, key_env)。"""
    try:
        import codex_model_router as R
    except Exception:
        return []
    return [(p, k) for p, _url, k in getattr(R, "ROUTES", []) if k]


def _resolve_fallback_item(item, providers: dict):
    """仿 model_gateway.fallback_candidates() 的切分：返回 (provider, model)，不落地则 None。

    fallback_chains 条目形如 "provider/model"，但模型名本身可能含 `/`（如 nvidia 家的
    `nvidia/nemotron-3-ultra-550b-a55b`，写作 "nvidia/nvidia/nemotron-3-...")。因此不按
    第一个斜杠硬切，而是逐个切点试，取「左侧是已注册供应商、右侧是该供应商已声明模型」
    的那个切点——与 model_gateway 的白名单守卫保持同一套判定，避免「检查器说能落地、
    运行时却丢弃」的两套口径。
    """
    if not isinstance(item, str) or "/" not in item:
        return None
    parts = [x.strip() for x in item.split("/")]
    for cut in range(1, len(parts)):
        pname = "/".join(parts[:cut])
        mname = "/".join(parts[cut:])
        if pname in providers and mname in (providers[pname].get("models") or {}):
            return (pname, mname)
    return None


def check_fallback_chains(providers: dict, fallback_chains: dict) -> tuple[list[str], list[str]]:
    """第五面：fallback_chains 的每个 provider/model 必须能在 providers[].models 落地。

    纯函数（只吃两个受控 dict，不碰任何文件），便于离线单测。
    分级口径：
    - 死引用（provider 不存在 或 model 未在该 provider 的 models 里）= 错误；
    - 空链（某 role 的候选列表为空）= 提示（非错误）——空链可能是有意的
      （"这个 role 不需要降级"），应由人判；但必须在提示里列出 role 名，不许沉默。
    返回 (errors, warnings)。
    """
    errors = []
    warnings = []
    for role in sorted(fallback_chains):
        chain = fallback_chains[role] or []
        if not chain:
            warnings.append(
                "W3 fallback_chains[%s] 空链：该 role 无降级候选（可能有意，请人工确认）" % role
            )
            continue
        for item in chain:
            if _resolve_fallback_item(item, providers) is None:
                errors.append(
                    "E10 fallback_chains[%s] 死引用 `%s`：provider 不存在 或 model 未在该 provider 声明"
                    % (role, item)
                )
    return errors, warnings


# E11 的「已知未接」清单：role -> 理由。这些 role 的默认模型悬空（resolve() 找不到
# 包含该模型的 provider，会兜底到第一个 provider 并用它的 key 请求一个它不认识的模型名
# → 必然失败），但没有客观依据能补默认值（例如无降级链首项），补它等于替用户选型。
# 命中清单 = 提示（非错误），留人判 / 另开卡。
KNOWN_UNCONNECTED = {
    "code_premium": "无降级链（fallback_chains 空），取不到「链首」客观依据；补默认模型等于替用户选型，留待另开卡",
}


def check_role_resolution(providers: dict, roles: dict, role_defaults: dict,
                          known_unconnected: dict) -> tuple[list[str], list[str]]:
    """第六面（E11）：每个 role 的「最终解析结果」对应的 model 必须能在某 provider 落地。

    本检查器查的是 model_gateway.resolve() 的**最终结果**，不是注册表某一层——所以取值
    顺序必须与 resolve() 逐条同构：
      1. 取值：`roles.get(role) or role_defaults.get(role)`（单一真源 roles 优先，再内置兜底）。
      2. 落地判定：该 model 是否出现在任一 provider 的 `models` 里（与 resolve() 找
         provider 的循环同构）；找不到 → resolve() 兜底到第一个 provider，用那把 key
         请求一个它不认识的模型名 → 必然失败（"悬空"）。

    纯函数（只吃受控 dict，不碰文件），便于离线单测。
    分级口径：
      - 悬空（model 无法在任何 provider 落地）= 错误；
      - 悬空且 role 命中「已知未接」清单 = 提示（非错误）。
    返回 (errors, warnings)。
    """
    errors = []
    warnings = []
    for role in sorted(set(roles) | set(role_defaults)):
        model = roles.get(role) or role_defaults.get(role)
        if not model:
            continue  # resolve() 会抛 ValueError，不在此覆盖（不属于"悬空"缺陷）
        landed = any(model in (pcfg.get("models") or {}) for pcfg in providers.values())
        if landed:
            continue
        if role in known_unconnected:
            warnings.append(
                "W4 role `%s` 最终解析模型 `%s` 悬空（已知未接）：%s"
                % (role, model, known_unconnected[role])
            )
        else:
            errors.append(
                "E11 role `%s` 最终解析模型 `%s` 无法在任何 provider 落地 -> resolve() 会兜底到第一个 provider"
                % (role, model)
            )
    return errors, warnings


def check():
    errors = []
    warnings = []

    fm, _body = AUDIT.load_master()
    providers = fm.get("providers") or {}
    mother_ids = set(providers)
    declared = declared_key_envs(fm)
    scan_exempt = fm.get("provider_scan_exempt") or {}
    workcopy_exempt = fm.get("provider_workcopy_exempt") or {}
    env_disposition = fm.get("env_keys_not_provider") or {}
    spec_by_id = {s["id"]: s for s in AUDIT.PROVIDER_SPECS}

    # E1: .env 有 key，但母本没声明、也没给归属
    for k in env_provider_keys():
        if k not in declared and k not in env_disposition:
            errors.append(
                "E1 .env 有 `%s`，母本既没有 provider 声明它，也没有写进 "
                "`env_keys_not_provider` 归属表 -> 疑似漏登记供应商" % k
            )

    work = {}
    fallback_chains = {}
    roles = {}
    if WORK_JSON.exists():
        work_full = json.loads(WORK_JSON.read_text(encoding="utf-8")) or {}
        work = work_full.get("providers") or {}
        fallback_chains = work_full.get("fallback_chains") or {}
        roles = work_full.get("roles") or {}

    # E2: 工作副本有 provider，但母本没有
    for pid in sorted(set(work) - mother_ids):
        errors.append("E2 工作副本有 provider `%s`，但母本没有 -> 母本漏登记" % pid)

    # E3: 母本有 provider，但既不在扫描器、也没给豁免理由
    for pid in sorted(mother_ids):
        if pid not in spec_by_id and pid not in scan_exempt:
            errors.append(
                "E3 母本 provider `%s` 不在 PROVIDER_SPECS（5 天扫描不覆盖），"
                "也没写进 `provider_scan_exempt` 说明理由 -> 登记了却没人扫" % pid
            )

    # E4: 扫描器有 provider，但母本没有
    for pid in sorted(set(spec_by_id) - mother_ids):
        errors.append("E4 扫描器有 provider `%s`，但母本没有 -> 扫描器多余/母本缺项" % pid)

    # E5: 母本内部 curated 与 models 键集必须一致
    for pid in sorted(mother_ids):
        cur = fm.get(pid + "_curated")
        if cur is None:
            continue
        mods = set((providers[pid].get("models") or {}))
        only_cur = set(cur) - mods
        only_mod = mods - set(cur)
        if only_cur:
            errors.append("E5 `%s`: 只在 %s_curated 不在 providers.%s.models -> %s"
                          % (pid, pid, pid, sorted(only_cur)))
        if only_mod:
            errors.append("E5 `%s`: 只在 providers.%s.models 不在 %s_curated -> %s"
                          % (pid, pid, pid, sorted(only_mod)))

    # E6: key_env 四方一致
    probe = AUDIT.PROBE_PROVIDERS
    for pid, spec in spec_by_id.items():
        pairs = {
            "母本": (providers.get(pid) or {}).get("key_env"),
            "扫描器": spec.get("key_env"),
            "工作副本": (work.get(pid) or {}).get("key_env"),
            "探针": (probe.get(pid) or {}).get("key"),
        }
        vals = {v for v in pairs.values() if v}
        if len(vals) > 1:
            errors.append("E6 `%s` key_env 不一致 -> %s"
                          % (pid, "，".join("%s=%s" % kv for kv in pairs.items())))

    # E7: Agent 路由/配置引用的 key_env 必须在母本声明过
    for pid, key in sorted(codex_provider_envs().items()):
        if key in ENV_REF_IGNORE:
            continue
        if key not in declared:
            errors.append("E7 `.codex/config.toml` provider `%s` 用的 `%s` 未在母本声明" % (pid, key))
        if pid not in mother_ids and PROVIDER_ALIAS.get(pid) not in mother_ids:
            warnings.append("W2 `.codex/config.toml` provider id `%s` 与母本不同名（别名未登记）" % pid)
    for prefix, key in sorted(set(router_routes())):
        if key in ENV_REF_IGNORE:
            continue
        if key not in declared:
            errors.append("E7 `codex_model_router.py` 路由 `%s` 用的 `%s` 未在母本声明" % (prefix, key))

    # W1: 母本有 provider，但工作副本没有
    for pid in sorted(mother_ids - set(work)):
        if pid in workcopy_exempt:
            continue
        warnings.append("W1 母本 provider `%s` 不在工作副本 model_providers.json（Agent 侧拿不到）" % pid)

    # E8/E9: §三 能力目录的内部一致性 + 覆盖完整性
    _body_full = AUDIT.VAULT_MASTER.read_text(encoding="utf-8", errors="replace")
    secm = re.search(r"## 三、能力目录.*?(?=### 专门模型的调用差异)", _body_full, re.S)
    if secm:
        sec = secm.group(0)
        in_sec = set()
        cur_sec = None
        for line in sec.split("\n"):
            hm = re.match(r"^### (.+?)—\s*(\d+) 个", line)
            if hm:
                cur_sec = (hm.group(1), int(hm.group(2)), 0)
                continue
            m = re.match(r"^- \*\*([a-z0-9\-]+)\*\*（(\d+)，采用 (\d+)）：(.*)$", line)
            if not m:
                continue
            pid, decl, adopt, rest = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            in_sec.add(pid)
            listed = len(re.findall(r"`[^`]+`", rest))
            stars = rest.count("★")
            if decl != listed:
                errors.append("E8 §三 `%s` 声明 %d 个，实际列出 %d 个 -> 计数与清单不符" % (pid, decl, listed))
            if adopt != stars:
                errors.append("E8 §三 `%s` 声明采用 %d 个，实际标 ★ %d 个 -> 计数与星标不符" % (pid, adopt, stars))
        for pid in sorted(mother_ids - in_sec):
            errors.append("E9 母本 provider `%s` 没有出现在 §三 能力目录 -> 目录不全" % pid)

    # E10/W3: fallback_chains 的 provider/model 引用必须能在工作副本 providers[].models 落地
    fb_errors, fb_warnings = check_fallback_chains(work, fallback_chains)
    errors.extend(fb_errors)
    warnings.extend(fb_warnings)

    # E11/W4: 每个 role 的最终解析模型必须能在某 provider 落地（resolve() 口径同构）
    rr_errors, rr_warnings = check_role_resolution(work, roles, ROLE_DEFAULTS, KNOWN_UNCONNECTED)
    errors.extend(rr_errors)
    warnings.extend(rr_warnings)

    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description="供应商一致性守卫（母本/扫描器/工作副本/Agent 四方对账）")
    ap.add_argument("--quiet", action="store_true", help="只输出问题")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    errors, warnings = check()
    if not args.quiet:
        print("母本：%s" % VAULT_MASTER)
        print("工作副本：%s" % WORK_JSON)
        print("扫描器：%d 家 ｜ 探针：%d 家" % (len(AUDIT.PROVIDER_SPECS), len(AUDIT.PROBE_PROVIDERS)))
        if KNOWN_UNCONNECTED:
            print("已知未接（role -> 理由，命中仅提示、不算错误）：")
            for _r, _why in sorted(KNOWN_UNCONNECTED.items()):
                print("  %s: %s" % (_r, _why))
        print("-" * 66)
    for e in errors:
        print(e)
    for w in warnings:
        print(w)
    print("-" * 66)
    print("结论：错误 %d ｜ 提示 %d -> %s"
          % (len(errors), len(warnings), "不一致，需修" if errors else "四方一致"))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
