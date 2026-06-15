# Three-Platform Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-safe three-platform publish orchestrator for Toutiao, Zhihu, and WeChat that blocks weak drafts, prevents duplicate publishes, and writes every platform result into one `pipeline-state.json`.

**Architecture:** Keep the existing browser automation scripts in place and add a Python control layer around them. The new layer owns preflight checks, the unified state file, derived per-platform payloads, subprocess execution, and post-publish state reconciliation from existing local records and debug artifacts.

**Tech Stack:** Python 3.11 standard library (`argparse`, `json`, `hashlib`, `pathlib`, `subprocess`, `tempfile`, `unittest`), existing Node.js Playwright scripts under `.tmp/`.

---

## File Map

**Create:**

- `C:\Users\Administrator\Documents\code-news\scripts\__init__.py`
- `C:\Users\Administrator\Documents\code-news\scripts\pipeline_state.py`
- `C:\Users\Administrator\Documents\code-news\scripts\platform_publish_adapters.py`
- `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py`
- `C:\Users\Administrator\Documents\code-news\tests\scripts\__init__.py`
- `C:\Users\Administrator\Documents\code-news\tests\scripts\test_pipeline_state.py`
- `C:\Users\Administrator\Documents\code-news\tests\scripts\test_quality_gate.py`
- `C:\Users\Administrator\Documents\code-news\tests\scripts\test_platform_publish_adapters.py`
- `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_three_platform_pipeline.py`

**Modify:**

- `C:\Users\Administrator\Documents\code-news\scripts\check_generated_article_quality.py`
- `C:\Users\Administrator\Documents\code-news\.tmp\publish_toutiao_article.js`

**Do not modify in this pass unless blocked:**

- `C:\Users\Administrator\Documents\code-news\.tmp\publish_zhihu_article_controlled.js`
- `C:\Users\Administrator\Documents\code-news\.tmp\publish_wechat_article_controlled.js`

The Zhihu and WeChat scripts already expose enough local records and debug artifacts for the orchestrator to reason safely. Toutiao needs one small semantics fix because it verifies the article in the remote list, then still stores local status as `submitted`.

---

### Task 1: Create Shared Pipeline State Utilities

**Files:**

- Create: `C:\Users\Administrator\Documents\code-news\scripts\__init__.py`
- Create: `C:\Users\Administrator\Documents\code-news\scripts\pipeline_state.py`
- Create: `C:\Users\Administrator\Documents\code-news\tests\scripts\__init__.py`
- Create: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_pipeline_state.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.pipeline_state import (
    build_fingerprint,
    initialize_pipeline_state,
    pipeline_state_path,
    set_platform_state,
    summarize_assets,
)


class PipelineStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.payload_path = self.root / ".tmp" / "toutiao_payload_demo.json"
        self.generated_dir = self.root / ".tmp" / "generated" / "demo-slug"
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path.parent.mkdir(parents=True, exist_ok=True)
        self.payload = {
            "slug": "demo-slug",
            "title": "A short title",
            "summary": "Concrete summary",
            "article_blocks": ["first block", "second block"],
            "body_images": [{"file_name": "body-01.png"}],
        }
        self.payload_path.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_fingerprint_ignores_whitespace_noise(self) -> None:
        altered = {
            **self.payload,
            "summary": "Concrete   summary",
            "article_blocks": ["first block", "second   block"],
        }
        self.assertEqual(build_fingerprint(self.payload), build_fingerprint(altered))

    def test_summarize_assets_reports_missing_body_images(self) -> None:
        (self.generated_dir / "cover.png").write_bytes(b"cover")
        asset_summary = summarize_assets(self.generated_dir, self.payload)
        self.assertEqual(asset_summary["coverExists"], True)
        self.assertEqual(asset_summary["bodyImageCount"], 0)
        self.assertIn("body-01.png", " ".join(asset_summary["missingFiles"]))

    def test_initialize_pipeline_state_contains_all_platforms(self) -> None:
        state = initialize_pipeline_state(self.payload_path, self.payload)
        self.assertEqual(state["slug"], "demo-slug")
        self.assertEqual(state["platforms"]["toutiao"]["status"], "ready")
        self.assertEqual(state["platforms"]["zhihu"]["status"], "ready")
        self.assertEqual(state["platforms"]["wechat"]["status"], "ready")

    def test_set_platform_state_updates_timestamp_and_error(self) -> None:
        state = initialize_pipeline_state(self.payload_path, self.payload)
        updated = set_platform_state(
            state,
            "wechat",
            status="awaiting_verification",
            error="wechat qr required",
        )
        self.assertEqual(updated["platforms"]["wechat"]["status"], "awaiting_verification")
        self.assertEqual(updated["platforms"]["wechat"]["error"], "wechat qr required")
        self.assertIsNotNone(updated["updatedAt"])

    def test_pipeline_state_path_lives_under_generated_slug_dir(self) -> None:
        state_path = pipeline_state_path(self.payload_path, self.payload)
        self.assertEqual(state_path, self.generated_dir / "pipeline-state.json")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.scripts.test_pipeline_state -v
```

Expected:

```text
ERROR: No module named 'scripts.pipeline_state'
```

- [ ] **Step 3: Write minimal implementation**

Create `C:\Users\Administrator\Documents\code-news\scripts\__init__.py`:

```python
"""Shared helpers for content pipeline scripts."""
```

Create `C:\Users\Administrator\Documents\code-news\scripts\pipeline_state.py`:

```python
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PLATFORM_KEYS = ("toutiao", "zhihu", "wechat")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def build_fingerprint(payload: dict[str, Any]) -> str:
    basis = {
        "title": normalize_text(payload.get("title")),
        "summary": normalize_text(payload.get("summary")),
        "article_blocks": [
            normalize_text(block) for block in payload.get("article_blocks", []) or []
        ],
    }
    return hashlib.sha256(
        json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def generated_dir_from_payload_path(payload_path: Path, payload: dict[str, Any]) -> Path:
    return payload_path.parent / "generated" / str(payload.get("slug") or payload_path.stem)


def pipeline_state_path(payload_path: Path, payload: dict[str, Any]) -> Path:
    return generated_dir_from_payload_path(payload_path, payload) / "pipeline-state.json"


def summarize_assets(generated_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    cover_exists = any((generated_dir / name).exists() for name in ("cover.png", "cover.jpg", "cover.jpeg"))
    if not cover_exists:
        missing.append("cover.png|cover.jpg|cover.jpeg")

    image_count = 0
    for index, item in enumerate(payload.get("body_images", []) or [], start=1):
        file_name = item.get("file_name") or f"body-{index:02d}.png"
        if (generated_dir / file_name).exists():
            image_count += 1
        else:
            missing.append(file_name)

    return {
        "coverExists": cover_exists,
        "bodyImageCount": image_count,
        "missingFiles": missing,
    }


def empty_platform_state() -> dict[str, Any]:
    return {
        "status": "ready",
        "attemptCount": 0,
        "lastAttemptAt": None,
        "publishedAt": None,
        "url": None,
        "titleUsed": None,
        "verificationSource": None,
        "error": None,
    }


def initialize_pipeline_state(payload_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    generated_dir = generated_dir_from_payload_path(payload_path, payload)
    return {
        "schemaVersion": 1,
        "slug": str(payload.get("slug") or payload_path.stem),
        "fingerprint": build_fingerprint(payload),
        "title": normalize_text(payload.get("title")),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "qualityGate": {},
        "assets": summarize_assets(generated_dir, payload),
        "platforms": {key: empty_platform_state() for key in PLATFORM_KEYS},
    }


def load_pipeline_state(state_path: Path) -> dict[str, Any]:
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_pipeline_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def set_platform_state(state: dict[str, Any], platform: str, **changes: Any) -> dict[str, Any]:
    next_state = deepcopy(state)
    next_state["platforms"][platform].update(changes)
    next_state["updatedAt"] = now_iso()
    return next_state
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest tests.scripts.test_pipeline_state -v
```

Expected:

```text
test_build_fingerprint_ignores_whitespace_noise ... ok
test_summarize_assets_reports_missing_body_images ... ok
test_initialize_pipeline_state_contains_all_platforms ... ok
test_set_platform_state_updates_timestamp_and_error ... ok
test_pipeline_state_path_lives_under_generated_slug_dir ... ok
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/__init__.py scripts/pipeline_state.py tests/scripts/__init__.py tests/scripts/test_pipeline_state.py
git commit -m "feat: add pipeline state utilities"
```

### Task 2: Upgrade Quality Check Into a Hard Gate

**Files:**

- Modify: `C:\Users\Administrator\Documents\code-news\scripts\check_generated_article_quality.py`
- Create: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_quality_gate.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from scripts.check_generated_article_quality import CheckResult, evaluate_gate


class QualityGateTests(unittest.TestCase):
    def test_score_below_80_blocks_even_without_fail_items(self) -> None:
        decision = evaluate_gate(
            score=79,
            checks=[CheckResult("warn", "title weak", "too long")],
            min_score=80,
        )
        self.assertEqual(decision["status"], "blocked")
        self.assertEqual(decision["reason"], "score_below_minimum")

    def test_any_fail_item_blocks_even_with_high_score(self) -> None:
        decision = evaluate_gate(
            score=92,
            checks=[CheckResult("fail", "opening weak", "too abstract")],
            min_score=80,
        )
        self.assertEqual(decision["status"], "blocked")
        self.assertEqual(decision["reason"], "contains_fail_items")

    def test_high_score_without_fail_items_passes(self) -> None:
        decision = evaluate_gate(
            score=84,
            checks=[CheckResult("warn", "title weak", "too long")],
            min_score=80,
        )
        self.assertEqual(decision["status"], "passed")
        self.assertEqual(decision["reason"], "ready_for_publish")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.scripts.test_quality_gate -v
```

Expected:

```text
ImportError: cannot import name 'evaluate_gate'
```

- [ ] **Step 3: Write minimal implementation**

Add the following function to `C:\Users\Administrator\Documents\code-news\scripts\check_generated_article_quality.py` below `score_checks`:

```python
def evaluate_gate(
    *,
    score: int,
    checks: list[CheckResult],
    min_score: int = 80,
) -> dict[str, Any]:
    has_fail = any(item.severity == "fail" for item in checks)
    if has_fail:
        return {
            "status": "blocked",
            "reason": "contains_fail_items",
            "score": score,
            "failCount": sum(1 for item in checks if item.severity == "fail"),
            "warnCount": sum(1 for item in checks if item.severity == "warn"),
        }
    if score < min_score:
        return {
            "status": "blocked",
            "reason": "score_below_minimum",
            "score": score,
            "failCount": 0,
            "warnCount": sum(1 for item in checks if item.severity == "warn"),
        }
    return {
        "status": "passed",
        "reason": "ready_for_publish",
        "score": score,
        "failCount": 0,
        "warnCount": sum(1 for item in checks if item.severity == "warn"),
    }
```

Then update `main()` so it computes `score = score_checks(checks)` once, writes:

```python
gate = evaluate_gate(score=score, checks=checks, min_score=80)
report["gate"] = gate
```

and adds CLI support for:

```python
parser.add_argument(
    "--exit-nonzero-on-block",
    action="store_true",
    help="Return exit code 2 when the quality gate blocks publish.",
)
```

Finally, before `return 0` in `main()`:

```python
if args.exit_nonzero_on_block and gate["status"] == "blocked":
    return 2
return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest tests.scripts.test_quality_gate -v
```

Expected:

```text
test_score_below_80_blocks_even_without_fail_items ... ok
test_any_fail_item_blocks_even_with_high_score ... ok
test_high_score_without_fail_items_passes ... ok
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/check_generated_article_quality.py tests/scripts/test_quality_gate.py
git commit -m "feat: add blocking quality gate"
```

### Task 3: Build the Orchestrator Preflight Layer

**Files:**

- Create: `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py`
- Modify: `C:\Users\Administrator\Documents\code-news\scripts\pipeline_state.py`
- Create: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_three_platform_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_three_platform_pipeline import (
    choose_platform_title,
    load_title_variants,
    run_preflight,
)


class PipelinePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.payload_dir = self.root / ".tmp"
        self.generated_dir = self.root / ".tmp" / "generated" / "demo-slug"
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path = self.payload_dir / "toutiao_payload_demo.json"
        self.payload = {
            "slug": "demo-slug",
            "title": "Base title",
            "summary": "Actionable summary",
            "article_blocks": ["first", "second"],
            "body_images": [{"file_name": "body-01.png"}],
        }
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        (self.generated_dir / "cover.png").write_bytes(b"cover")
        (self.generated_dir / "body-01.png").write_bytes(b"body")
        (self.generated_dir / "title-variants.md").write_text(
            "# 平台标题方案\n\n## 今日头条\n\n短标题\n\n## 微信公众号\n\n长标题版本\n\n## 知乎\n\n问句标题版本\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_title_variants_parses_platform_sections(self) -> None:
        variants = load_title_variants(self.generated_dir / "title-variants.md")
        self.assertEqual(variants["toutiao"][0], "短标题")
        self.assertEqual(variants["wechat"][0], "长标题版本")
        self.assertEqual(variants["zhihu"][0], "问句标题版本")

    def test_choose_platform_title_uses_platform_specific_variant(self) -> None:
        variants = {"toutiao": ["短标题"], "wechat": ["长标题版本"], "zhihu": ["问句标题版本"]}
        self.assertEqual(choose_platform_title("toutiao", variants, "Base title"), "短标题")
        self.assertEqual(choose_platform_title("wechat", variants, "Base title"), "长标题版本")
        self.assertEqual(choose_platform_title("zhihu", variants, "Base title"), "问句标题版本")

    def test_run_preflight_writes_pipeline_state_and_platform_payloads(self) -> None:
        result = run_preflight(self.payload_path, min_score=0)
        self.assertEqual(result["gate"]["status"], "passed")
        self.assertTrue(result["statePath"].exists())
        self.assertTrue((self.generated_dir / "platform-payloads" / "toutiao.json").exists())
        self.assertTrue((self.generated_dir / "platform-payloads" / "zhihu.json").exists())
        self.assertTrue((self.generated_dir / "platform-payloads" / "wechat.json").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.scripts.test_run_three_platform_pipeline -v
```

Expected:

```text
ERROR: No module named 'scripts.run_three_platform_pipeline'
```

- [ ] **Step 3: Write minimal implementation**

Create `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.check_generated_article_quality import build_checks, evaluate_gate, read_json, read_metrics_rows, recent_payloads, score_checks, infer_topic_from_payload
from scripts.pipeline_state import initialize_pipeline_state, pipeline_state_path


def normalize_platform_heading(text: str) -> str:
    lowered = text.lower()
    if "头条" in text or "toutiao" in lowered:
        return "toutiao"
    if "微信" in text or "wechat" in lowered:
        return "wechat"
    if "知乎" in text or "zhihu" in lowered:
        return "zhihu"
    return lowered


def load_title_variants(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    variants: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current = normalize_platform_heading(line[3:].strip())
            variants.setdefault(current, [])
            continue
        if current and not line.startswith("#"):
            variants[current].append(line)
    return variants


def choose_platform_title(platform: str, variants: dict[str, list[str]], fallback: str) -> str:
    options = [item for item in variants.get(platform, []) if item.strip()]
    return options[0] if options else fallback


def write_platform_payloads(generated_dir: Path, payload: dict[str, Any], variants: dict[str, list[str]]) -> dict[str, Path]:
    payload_dir = generated_dir / "platform-payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for platform in ("toutiao", "zhihu", "wechat"):
        next_payload = dict(payload)
        next_payload["title"] = choose_platform_title(platform, variants, str(payload.get("title", "")))
        target = payload_dir / f"{platform}.json"
        target.write_text(json.dumps(next_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result[platform] = target
    return result


def run_preflight(payload_path: Path, min_score: int = 80) -> dict[str, Any]:
    payload = read_json(payload_path)
    checks = build_checks(payload, read_metrics_rows(Path("C:/Users/Administrator/Documents/code-news/.tmp/latest-content-performance-log.csv")), recent_payloads(payload_path))
    score = score_checks(checks)
    gate = evaluate_gate(score=score, checks=checks, min_score=min_score)
    state = initialize_pipeline_state(payload_path, payload)
    state["qualityGate"] = gate
    generated_dir = payload_path.parent / "generated" / str(payload["slug"])
    variants = load_title_variants(generated_dir / "title-variants.md")
    platform_payloads = write_platform_payloads(generated_dir, payload, variants)
    state_path = pipeline_state_path(payload_path, payload)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "payload": payload,
        "gate": gate,
        "statePath": state_path,
        "platformPayloads": platform_payloads,
        "topic": infer_topic_from_payload(payload),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest tests.scripts.test_run_three_platform_pipeline -v
```

Expected:

```text
test_load_title_variants_parses_platform_sections ... ok
test_choose_platform_title_uses_platform_specific_variant ... ok
test_run_preflight_writes_pipeline_state_and_platform_payloads ... ok
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/run_three_platform_pipeline.py scripts/pipeline_state.py tests/scripts/test_run_three_platform_pipeline.py
git commit -m "feat: add pipeline preflight orchestrator"
```

### Task 4: Add Platform Result Adapters and Safe Status Mapping

**Files:**

- Create: `C:\Users\Administrator\Documents\code-news\scripts\platform_publish_adapters.py`
- Modify: `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py`
- Create: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_platform_publish_adapters.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.platform_publish_adapters import (
    map_toutiao_result,
    map_wechat_result,
    should_skip_platform,
)


class PlatformPublishAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_should_skip_when_platform_already_verified(self) -> None:
        state = {"platforms": {"toutiao": {"status": "published_verified"}}}
        self.assertTrue(should_skip_platform(state, "toutiao"))

    def test_toutiao_submitted_plus_remote_list_hit_becomes_published_verified(self) -> None:
        record = {"status": "submitted", "pageUrl": "https://www.toutiao.com/item/1/"}
        verification = {"hasTitleMatch": True, "checkedAt": "2026-06-09T12:00:00+08:00"}
        mapped = map_toutiao_result(record, verification)
        self.assertEqual(mapped["status"], "published_verified")
        self.assertEqual(mapped["verificationSource"], "article_list_check")

    def test_wechat_awaiting_verification_does_not_allow_republish(self) -> None:
        record = {"status": "awaiting_wechat_verification", "pageUrl": "https://mp.weixin.qq.com/"}
        mapped = map_wechat_result(record)
        self.assertEqual(mapped["status"], "awaiting_verification")
        self.assertEqual(mapped["verificationSource"], "local_publish_record")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.scripts.test_platform_publish_adapters -v
```

Expected:

```text
ERROR: No module named 'scripts.platform_publish_adapters'
```

- [ ] **Step 3: Write minimal implementation**

Create `C:\Users\Administrator\Documents\code-news\scripts\platform_publish_adapters.py`:

```python
from __future__ import annotations

from typing import Any


def should_skip_platform(state: dict[str, Any], platform: str) -> bool:
    status = str(state["platforms"][platform]["status"])
    return status in {"published_verified", "duplicate_blocked"}


def map_toutiao_result(record: dict[str, Any] | None, verification: dict[str, Any] | None) -> dict[str, Any]:
    if verification and verification.get("hasTitleMatch"):
        return {
            "status": "published_verified",
            "publishedAt": record.get("submittedAt") if record else verification.get("checkedAt"),
            "url": (record or {}).get("pageUrl"),
            "verificationSource": "article_list_check",
            "error": None,
        }
    if record and record.get("status") == "verification_failed":
        return {
            "status": "publish_failed",
            "publishedAt": None,
            "url": record.get("pageUrl"),
            "verificationSource": "article_list_check",
            "error": "toutiao verification failed",
        }
    return {
        "status": "awaiting_verification",
        "publishedAt": None,
        "url": (record or {}).get("pageUrl"),
        "verificationSource": "local_publish_record",
        "error": None,
    }


def map_zhihu_result(record: dict[str, Any] | None) -> dict[str, Any]:
    if record and record.get("publishedAt"):
        return {
            "status": "published_verified",
            "publishedAt": record.get("publishedAt"),
            "url": record.get("url"),
            "verificationSource": "local_publish_record",
            "error": None,
        }
    return {
        "status": "publish_failed",
        "publishedAt": None,
        "url": None,
        "verificationSource": "local_publish_record",
        "error": "zhihu publish record missing",
    }


def map_wechat_result(record: dict[str, Any] | None) -> dict[str, Any]:
    status = str((record or {}).get("status") or "")
    if status == "published" or record and record.get("publishedAt"):
        return {
            "status": "published_verified",
            "publishedAt": record.get("publishedAt"),
            "url": record.get("pageUrl"),
            "verificationSource": str(record.get("source") or "local_publish_record"),
            "error": None,
        }
    if status == "awaiting_wechat_verification":
        return {
            "status": "awaiting_verification",
            "publishedAt": None,
            "url": record.get("pageUrl"),
            "verificationSource": "local_publish_record",
            "error": None,
        }
    if status in {"remote_publish_pending", "remote_publish_pending_preflight"}:
        return {
            "status": "awaiting_verification",
            "publishedAt": None,
            "url": record.get("pageUrl"),
            "verificationSource": str(record.get("source") or "local_publish_record"),
            "error": None,
        }
    return {
        "status": "publish_failed",
        "publishedAt": None,
        "url": (record or {}).get("pageUrl"),
        "verificationSource": "local_publish_record",
        "error": "wechat publish result unresolved",
    }
```

Then update `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py` to import and use:

```python
from scripts.platform_publish_adapters import map_toutiao_result, map_zhihu_result, map_wechat_result, should_skip_platform
```

and keep all platform-state transitions inside the Python orchestrator, not inside ad hoc `if` branches.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m unittest tests.scripts.test_platform_publish_adapters -v
```

Expected:

```text
test_should_skip_when_platform_already_verified ... ok
test_toutiao_submitted_plus_remote_list_hit_becomes_published_verified ... ok
test_wechat_awaiting_verification_does_not_allow_republish ... ok
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/platform_publish_adapters.py scripts/run_three_platform_pipeline.py tests/scripts/test_platform_publish_adapters.py
git commit -m "feat: add platform publish adapters"
```

### Task 5: Wire Real Publish Execution and Fix Toutiao Status Semantics

**Files:**

- Modify: `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py`
- Modify: `C:\Users\Administrator\Documents\code-news\.tmp\publish_toutiao_article.js`
- Modify: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_three_platform_pipeline.py`

- [ ] **Step 1: Extend the failing pipeline tests to cover subprocess execution and skip logic**

Append to `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_three_platform_pipeline.py`:

```python
from unittest.mock import patch

from scripts.run_three_platform_pipeline import run_pipeline


    @patch("scripts.run_three_platform_pipeline.subprocess.run")
    def test_run_pipeline_skips_verified_platform_and_runs_remaining_two(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = '{"status":"published","pageUrl":"https://example.com"}'
        run_mock.return_value.stderr = ""

        state_path = self.generated_dir / "pipeline-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "slug": "demo-slug",
                    "fingerprint": "x",
                    "title": "Base title",
                    "createdAt": "2026-06-09T12:00:00+08:00",
                    "updatedAt": "2026-06-09T12:00:00+08:00",
                    "qualityGate": {"status": "passed", "score": 90, "failCount": 0, "warnCount": 0},
                    "assets": {"coverExists": True, "bodyImageCount": 1, "missingFiles": []},
                    "platforms": {
                        "toutiao": {"status": "published_verified"},
                        "zhihu": {"status": "ready"},
                        "wechat": {"status": "ready"},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = run_pipeline(self.payload_path, min_score=0)
        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(result["platforms"]["toutiao"]["status"], "published_verified")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.scripts.test_run_three_platform_pipeline -v
```

Expected:

```text
AttributeError: module 'scripts.run_three_platform_pipeline' has no attribute 'run_pipeline'
```

- [ ] **Step 3: Implement the real publish loop and the Toutiao status fix**

Update `C:\Users\Administrator\Documents\code-news\.tmp\publish_toutiao_article.js` at the successful post-verification save block:

```javascript
    savePublishRecord(publishRecordsPath, {
      title: payload.title,
      slug: payload.slug,
      contentFingerprint,
      status: "published",
      submittedAt: verification.checkedAt,
      pageUrl: verification.pageUrl,
      debugDir,
      verificationSource: "article_list_check",
    });
```

Then extend `C:\Users\Administrator\Documents\code-news\scripts\run_three_platform_pipeline.py` with a real publish loop:

```python
import subprocess

from scripts.pipeline_state import load_pipeline_state, now_iso, save_pipeline_state, set_platform_state
from scripts.platform_publish_adapters import (
    map_toutiao_result,
    map_zhihu_result,
    map_wechat_result,
    should_skip_platform,
)


PLATFORM_COMMANDS = {
    "toutiao": ["node", "C:/Users/Administrator/Documents/code-news/.tmp/publish_toutiao_article.js"],
    "zhihu": ["node", "C:/Users/Administrator/Documents/code-news/.tmp/publish_zhihu_article_controlled.js"],
    "wechat": ["node", "C:/Users/Administrator/Documents/code-news/.tmp/publish_wechat_article_controlled.js"],
}


def run_platform_command(platform: str, payload_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*PLATFORM_COMMANDS[platform], str(payload_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def reconcile_platform_state(state: dict[str, Any], platform: str, preflight: dict[str, Any]) -> dict[str, Any]:
    payload = preflight["payload"]
    generated_dir = preflight["statePath"].parent

    if platform == "toutiao":
        records_path = Path("C:/Users/Administrator/Documents/code-news/.tmp/toutiao-publish-records.json")
        record_rows = json.loads(records_path.read_text(encoding="utf-8")) if records_path.exists() else []
        record = next(
            (
                item for item in record_rows
                if item.get("slug") == payload.get("slug") or item.get("title") == payload.get("title")
            ),
            None,
        )
        verification_path = generated_dir / "debug" / "after-publish-list-check.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8")) if verification_path.exists() else None
        mapped = map_toutiao_result(record, verification)
        return set_platform_state(state, "toutiao", **mapped)

    if platform == "zhihu":
        records_path = Path("C:/Users/Administrator/Documents/code-news/.tmp/zhihu-publish-records.json")
        record_rows = json.loads(records_path.read_text(encoding="utf-8")) if records_path.exists() else []
        record = next(
            (
                item for item in record_rows
                if item.get("slug") == payload.get("slug") or item.get("title") == payload.get("title")
            ),
            None,
        )
        mapped = map_zhihu_result(record)
        return set_platform_state(state, "zhihu", **mapped)

    records_path = Path("C:/Users/Administrator/Documents/code-news/.tmp/wechat-publish-records.json")
    record_rows = json.loads(records_path.read_text(encoding="utf-8")) if records_path.exists() else []
    record = next(
        (
            item for item in record_rows
            if item.get("slug") == payload.get("slug") or item.get("title") == payload.get("title")
        ),
        None,
    )
    mapped = map_wechat_result(record)
    return set_platform_state(state, "wechat", **mapped)


def run_pipeline(payload_path: Path, min_score: int = 80) -> dict[str, Any]:
    preflight = run_preflight(payload_path, min_score=min_score)
    state_path = preflight["statePath"]
    state = load_pipeline_state(state_path)
    if preflight["gate"]["status"] != "passed":
        return state

    for platform in ("toutiao", "zhihu", "wechat"):
        if should_skip_platform(state, platform):
            continue
        state = set_platform_state(
            state,
            platform,
            status="publishing",
            attemptCount=int(state["platforms"][platform].get("attemptCount", 0)) + 1,
            lastAttemptAt=now_iso(),
            titleUsed=json.loads(preflight["platformPayloads"][platform].read_text(encoding="utf-8"))["title"],
        )
        save_pipeline_state(state_path, state)
        run_platform_command(platform, preflight["platformPayloads"][platform])
        state = reconcile_platform_state(state, platform, preflight)
        save_pipeline_state(state_path, state)

    return state
```

- [ ] **Step 4: Run tests and syntax checks**

Run:

```powershell
python -m unittest tests.scripts.test_run_three_platform_pipeline -v
node --check C:\Users\Administrator\Documents\code-news\.tmp\publish_toutiao_article.js
node --check C:\Users\Administrator\Documents\code-news\.tmp\publish_zhihu_article_controlled.js
node --check C:\Users\Administrator\Documents\code-news\.tmp\publish_wechat_article_controlled.js
```

Expected:

```text
test_load_title_variants_parses_platform_sections ... ok
test_choose_platform_title_uses_platform_specific_variant ... ok
test_run_preflight_writes_pipeline_state_and_platform_payloads ... ok
test_run_pipeline_skips_verified_platform_and_runs_remaining_two ... ok
```

and no output from the three `node --check` commands.

- [ ] **Step 5: Commit**

```powershell
git add scripts/run_three_platform_pipeline.py tests/scripts/test_run_three_platform_pipeline.py .tmp/publish_toutiao_article.js
git commit -m "feat: orchestrate three-platform publish pipeline"
```

---

## Self-Review

### Spec coverage

- Unified `pipeline-state.json`: Task 1
- Hard quality gate: Task 2
- Preflight + per-platform payloads: Task 3
- Duplicate-safe status mapping: Task 4
- Real publish orchestration and Toutiao semantics fix: Task 5

No spec section is left without a task.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later”
- Every task has exact file paths
- Every code step has concrete code blocks
- Every verification step has exact commands

### Type consistency

Shared names are consistent across tasks:

- `build_fingerprint`
- `pipeline_state_path`
- `set_platform_state`
- `evaluate_gate`
- `run_preflight`
- `run_pipeline`
- `map_toutiao_result`
- `map_zhihu_result`
- `map_wechat_result`

No later task introduces a mismatched helper name.
