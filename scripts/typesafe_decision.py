#!/usr/bin/env python3
"""typesafe_decision.py — TypeSafe AI「Jev」决策模型调用入口（Jev 不是 chat 模型）。

Jev 是 System One 决策模型：**不生成文本、不聊天**，因此不能当 Codex/Claude 的对话模型用
（官方文档 https://docs.typesafe.ai/introduction/coding-agents 明确写了这一点）。
一次调用 = 一个 state（文本或 JSON）+ 一组 typed questions → 一组结构化概率答案：

    choice  → choice / probabilities / confidence
    score   → score / probabilities / confidence / legend
    noul    → noul（0–1，即「该判断为真」的概率）

所以它在本仓库的定位是「给代码消费的判断原语」，与 LLM 供应商是两套东西。
questions 直接使用官方 schema 原样透传，本脚本不自立 DSL。

接口：POST https://api.typesafe.ai/v1/systemone   Authorization: Bearer <TYPESAFE_API_KEY>
文档索引：https://docs.typesafe.ai/llms.txt
Key 位置：宿主集中存放处 ~/.hermes/.env（取 key 复用唯一入口 ~/.hermes/scripts/hermes_env.py）。
进程环境优先 —— 每个信任域可以自注入（Claude Code 的 settings.json env 块 / DSH 的
~/.dsh/.credentials.yaml / OpenClaw compose 的 environment）；跨文件系统边界（WSL、容器）
时再回退到该文件在 /mnt/c 的等价挂载，所以同一份脚本在宿主机与 WSL 里都能直接跑。

用法：
    python scripts/typesafe_decision.py --selftest
    python scripts/typesafe_decision.py --state "文本" --questions-file q.json
    python scripts/typesafe_decision.py --state-file s.txt --questions-file q.json --out ans.json

questions 文件示例（官方 schema）：
    {
      "department": {"type": "choice", "instructions": "该由哪个团队处理",
                     "criteria": {"billing": "付费问题", "technical": "集成故障"}},
      "is_urgent":   {"type": "noul", "instructions": "消息表达了紧迫性"}
    }

退出码：0 成功 / 2 缺 key / 3 上游或网络错误 / 4 用法错误
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.typesafe.ai/v1"
SYSTEMONE_URL = API_BASE + "/systemone"
MODELS_URL = API_BASE + "/models"
KEY_NAME = "TYPESAFE_API_KEY"
DEFAULT_MODEL = "jev-latest"
HERMES_HOME_DIR = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
KEY_STORE = HERMES_HOME_DIR / ".env"
# 跨文件系统边界的兜底：宿主集中存放处（.hermes/.env）在别的信任域里的**等价挂载视图**。
#   · WSL（DSH）：/mnt/c/... 可读，但 WSL 的 $HOME 是 /home/ubuntu、HERMES_HOME 默认指向那里，
#     于是 hermes_env 找不到宿主那份 .env —— 2026-10-15 实测 DSH 侧报「缺 key」exit 2。
#   · 容器（OpenClaw）：正常靠 compose 注入 TYPESAFE_API_KEY；注入没生效时才走到这里。
# 这两个只是**同一份文件**的不同挂载视图，不构成第二份副本 —— 集中存放处仍然只有一份。
FALLBACK_HOMES = (Path(r"C:\Users\Administrator\.hermes"),
                  Path("/mnt/c/Users/Administrator/.hermes"))


def _die(code: int, message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def lookup_key() -> str:
    """取 key：进程环境 → $HERMES_HOME/.env → 跨域等价挂载，全程只走 hermes_env 这一个读口。

    进程环境优先，是为了让每个信任域用自己的机制注入 key：Claude Code 走 settings.json 的
    env 块、DSH 走 ~/.dsh/.credentials.yaml、OpenClaw 走 compose 的 environment。
    宿主侧的集中存放处（~/.hermes/.env）由 hermes_env 直接读；跨了文件系统边界时
    （WSL / 容器），把 HERMES_HOME 临时指向等价挂载再问同一个读口 —— 这样既不另抄一份
    .env 解析（`hermes_env.py` 自述「不要再抄第 N 份 load_env()」），也不用改那个被
    20+ 个脚本共用的入口。
    """
    homes = (HERMES_HOME_DIR,) + FALLBACK_HOMES

    if os.environ.get(KEY_NAME):          # ⓪ 各信任域自注入的 key 最优先
        return os.environ[KEY_NAME]

    reader = _find_reader(homes)          # ① 先把「唯一读口」找到（只做一次）
    if reader is None:
        _die(2, "[缺 key] 找不到取 key 的唯一入口 hermes_env.py，找过："
                + "、".join(str(h / "scripts" / "hermes_env.py") for h in homes))

    # ② 逐个候选 home 问同一个读口（临时把 HERMES_HOME 指过去）
    tried: list[str] = []
    for home in homes:
        store = home / ".env"
        tried.append(str(store))
        if not store.is_file():
            continue

        saved = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(home)
        try:
            key = reader(KEY_NAME)
        finally:
            if saved is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = saved
        if key:
            return key

    _die(2, f"[缺 key] 进程环境里没有 {KEY_NAME}，也没在这些集中存放处找到该行："
            + "、".join(tried))


def _find_reader(homes: tuple[Path, ...]):
    """从各候选 home 的 scripts/ 下拿到 hermes_env.env（取 key 的唯一读口）；找不到返回 None。"""
    for home in homes:
        scripts = home / "scripts"
        if not (scripts / "hermes_env.py").is_file():
            continue
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        try:
            from hermes_env import env as hermes_env  # type: ignore
        except ImportError:
            continue
        return hermes_env
    return None


def _request(url: str, key: str, payload: dict | None, timeout: float) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data else "GET",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1500]
        _die(3, f"[上游错误] HTTP {exc.code} {url}\n{detail}")
    except urllib.error.URLError as exc:
        _die(3, f"[网络错误] {url}: {exc.reason}")
    except json.JSONDecodeError as exc:
        _die(3, f"[响应解析失败] {url}: {exc}")


def read_json(path: str, what: str) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        _die(4, f"[用法错误] 读不到{what} {path}: {exc}")
    except json.JSONDecodeError as exc:
        _die(4, f"[用法错误] {what}不是合法 JSON：{path}: {exc}")


# ---------------------------------------------------------------- selftest

SELFTEST_STATE = (
    "Our API integration started returning 500 errors on every request about 20 minutes ago, "
    "and we cannot process any customer orders until this is fixed."
)
SELFTEST_QUESTIONS = {
    "is_urgent": {"type": "noul", "instructions": "The message conveys urgency or time-sensitivity"},
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this",
        "criteria": {
            "billing": "Payment or subscription issues",
            "technical": "Bugs or integration problems",
            "sales": "Pricing or account questions",
        },
    },
    "frustration": {
        "type": "score",
        "instructions": "How frustrated the customer appears",
        "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"],
    },
}


def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  → ' + detail if detail else ''}")
    return ok


def _unit(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= float(value) <= 1.0


def selftest(model: str, timeout: float) -> int:
    key = lookup_key()
    ok = True

    print(f"[1/2] 连通性 {MODELS_URL}")
    models = _request(MODELS_URL, key, None, timeout).get("models") or []
    names = [m.get("name") for m in models]
    ok &= _check("GET /v1/models 返回模型列表", bool(names), ", ".join(str(n) for n in names))
    ok &= _check("列表里有 jev-latest 别名", "jev-latest" in names)

    print(f"[2/2] 真实决策调用 {SYSTEMONE_URL}（model={model}）")
    resp = _request(SYSTEMONE_URL, key, {"model": model, "state": SELFTEST_STATE,
                                         "questions": SELFTEST_QUESTIONS}, timeout)
    answers = resp.get("answers") or {}
    ok &= _check("三类问题各自有答案", set(answers) == set(SELFTEST_QUESTIONS),
                 ", ".join(sorted(answers)))

    noul = answers.get("is_urgent") or {}
    ok &= _check("noul 是 0–1 的数", _unit(noul.get("noul")), f"noul={noul.get('noul')}")

    choice = answers.get("department") or {}
    probs = choice.get("probabilities") or {}
    ok &= _check("choice 落在 criteria 选项里", choice.get("choice") in SELFTEST_QUESTIONS["department"]["criteria"],
                 f"choice={choice.get('choice')}")
    ok &= _check("choice 每项概率 0–1 且和为 1",
                 bool(probs) and all(_unit(v) for v in probs.values()) and abs(sum(probs.values()) - 1.0) < 0.02,
                 f"sum={sum(probs.values()):.3f}")
    ok &= _check("choice 带 confidence", _unit(choice.get("confidence")), f"confidence={choice.get('confidence')}")

    score = answers.get("frustration") or {}
    legend = score.get("legend") or {}
    ok &= _check("score 命中 rubric 且带 legend",
                 isinstance(score.get("score"), (int, float)) and bool(legend),
                 f"score={score.get('score')} legend={len(legend)} 级")

    print(f"\n响应原文（model={resp.get('model')}，usage={resp.get('usage')}）：")
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    print("\n" + ("✅ selftest 通过" if ok else "❌ selftest 不通过"))
    return 0 if ok else 3


# ---------------------------------------------------------------- main

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="调用 TypeSafe AI 的 Jev 决策模型（返回概率，不是文本生成）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--state", help="待判断的文本（或 JSON 字符串）")
    ap.add_argument("--state-file", help="从文件读 state（文本或 JSON）")
    ap.add_argument("--questions-file", help="问题单 JSON，官方 schema 原样透传")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"模型或别名（默认 {DEFAULT_MODEL}）")
    ap.add_argument("--out", help="把完整响应写到该文件")
    ap.add_argument("--timeout", type=float, default=120.0, help="超时秒数（默认 120）")
    ap.add_argument("--selftest", action="store_true", help="连通性 + 真实调用自检，不读 state/questions")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.selftest:
        return selftest(args.model, args.timeout)

    if bool(args.state) == bool(args.state_file):
        _die(4, "[用法错误] --state 与 --state-file 必须且只能给一个")
    if not args.questions_file:
        _die(4, "[用法错误] 必须给 --questions-file（或改用 --selftest）")

    if args.state_file:
        try:
            state = Path(args.state_file).read_text(encoding="utf-8")
        except OSError as exc:
            _die(4, f"[用法错误] 读不到 state 文件 {args.state_file}: {exc}")
    else:
        state = args.state

    questions = read_json(args.questions_file, "questions 文件")
    if not isinstance(questions, dict) or not questions:
        _die(4, "[用法错误] questions 必须是非空对象：{\"<id>\": {\"type\": \"noul|choice|score\", ...}}")

    key = lookup_key()
    resp = _request(SYSTEMONE_URL, key,
                    {"model": args.model, "state": state, "questions": questions}, args.timeout)
    text = json.dumps(resp, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"\n[已写入] {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
