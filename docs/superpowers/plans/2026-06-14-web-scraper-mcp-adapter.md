# Web Scraper MCP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repo-local `web_scraper_mcp` adapter that normalizes benchmark records, supports deterministic local providers, and writes reusable benchmark monitoring artifacts.

**Architecture:** Keep the adapter contract and normalization helpers in focused Python modules under `scripts/`, using the existing flat script layout. Implement only local, testable providers in this phase: `fixture` for repeatable tests and `import_json` for importing browser-exported or manually collected records. Add one orchestration script that turns normalized records into `benchmark-records.jsonl` and `benchmark-monitor.md` so the first step of the content chain stops depending on manual stitching.

**Tech Stack:** Python 3 standard library, JSON/JSONL files, `unittest`, existing `scripts/` + `tests/scripts/` layout

---

### File Structure

**Create:**
- `config/web_scraper_mcp.json`
- `scripts/web_scraper_contracts.py`
- `scripts/web_scraper_mcp.py`
- `scripts/run_benchmark_monitor.py`
- `tests/scripts/test_web_scraper_contracts.py`
- `tests/scripts/test_web_scraper_mcp.py`
- `tests/scripts/test_run_benchmark_monitor.py`

**Modify:**
- `config/tool_registry.json`

**Do not modify in this plan:**
- `scripts/run_v3_content_ops.py`
- `scripts/run_three_platform_pipeline.py`
- any formal publish scripts

### Task 1: Add Contract Tests for Normalized Scraper Records

**Files:**
- Create: `tests/scripts/test_web_scraper_contracts.py`
- Create: `scripts/web_scraper_contracts.py`

- [ ] **Step 1: Write the failing contract tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.web_scraper_contracts import normalize_record, write_jsonl


class WebScraperContractsTests(unittest.TestCase):
    def test_normalize_record_maps_alias_metrics_and_preserves_source_fields(self) -> None:
        raw = {
            "platform": "Zhihu",
            "title": "设计工具怎么选，先看4个判断",
            "url": "https://example.com/post",
            "author": "示例作者",
            "publishedAt": "2026-06-14T08:30:00+08:00",
            "summary": "先看结果能不能继续改，再看工具值不值得长期用。",
            "metrics": {
                "read_count": "1200",
                "likes": "23",
                "comment_count": "4",
                "favorites": "5",
            },
            "tags": ["AI工具", "效率"],
        }

        record = normalize_record(raw, capture_method="import_json")

        self.assertEqual(record["platform"], "zhihu")
        self.assertEqual(record["recordType"], "article")
        self.assertEqual(record["metrics"]["views"], 1200)
        self.assertEqual(record["metrics"]["likes"], 23)
        self.assertEqual(record["metrics"]["comments"], 4)
        self.assertEqual(record["metrics"]["favorites"], 5)
        self.assertEqual(record["meta"]["captureMethod"], "import_json")
        self.assertEqual(record["meta"]["sourceFields"]["author"], "示例作者")

    def test_normalize_record_requires_title_or_summary(self) -> None:
        raw = {
            "platform": "toutiao",
            "url": "https://example.com/post",
            "metrics": {"views": 12},
        }

        with self.assertRaises(ValueError):
            normalize_record(raw, capture_method="fixture")

    def test_write_jsonl_writes_utf8_lines(self) -> None:
        rows = [
            normalize_record(
                {
                    "platform": "wechat",
                    "title": "AI图片越真实，越要先做4步避坑",
                    "url": "https://example.com/a",
                    "summary": "正文摘要",
                },
                capture_method="fixture",
            )
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            write_jsonl(path, rows)
            content = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(content), 1)
            parsed = json.loads(content[0])
            self.assertEqual(parsed["platform"], "wechat")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm the module is missing**

Run:

```powershell
python -m unittest tests.scripts.test_web_scraper_contracts -v
```

Expected: FAIL with `ModuleNotFoundError` for `scripts.web_scraper_contracts` or missing attributes.

- [ ] **Step 3: Implement the normalization contract**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


METRIC_ALIASES = {
    "views": ("views", "view_count", "read_count", "reads"),
    "likes": ("likes", "like_count"),
    "comments": ("comments", "comment_count"),
    "favorites": ("favorites", "bookmarks", "favorite_count", "bookmark_count"),
    "shares": ("shares", "share_count"),
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def normalize_platform(value: Any) -> str:
    text = normalize_text(value).lower()
    aliases = {
        "jinritoutiao": "toutiao",
        "今日头条": "toutiao",
        "头条": "toutiao",
        "公众号": "wechat",
        "微信公众号": "wechat",
        "weixin": "wechat",
        "wechat": "wechat",
        "知乎": "zhihu",
        "zhihu": "zhihu",
        "小红书": "xiaohongshu",
        "xhs": "xiaohongshu",
    }
    return aliases.get(text, text or "unknown")


def to_int(value: Any) -> int:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0
    try:
        return max(0, int(float(text)))
    except ValueError:
        return 0


def normalize_metrics(payload: dict[str, Any]) -> dict[str, int]:
    metrics_source = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
    normalized: dict[str, int] = {}
    for target, aliases in METRIC_ALIASES.items():
        value = 0
        for alias in aliases:
            if alias in metrics_source:
                value = to_int(metrics_source.get(alias))
                break
        normalized[target] = value
    return normalized


def normalize_record(
    payload: dict[str, Any],
    *,
    platform: str | None = None,
    record_type: str = "article",
    capture_method: str = "unknown",
) -> dict[str, Any]:
    title = normalize_text(payload.get("title"))
    summary = normalize_text(payload.get("summary") or payload.get("content") or payload.get("excerpt"))
    url = normalize_text(payload.get("url"))
    author = normalize_text(payload.get("author") or payload.get("account_name") or payload.get("source"))

    if not title and not summary:
        raise ValueError("normalized record requires title or summary")

    tags = [normalize_text(item) for item in payload.get("tags", []) or [] if normalize_text(item)]
    published_at = normalize_text(payload.get("publishedAt") or payload.get("publish_time") or payload.get("post_date"))

    return {
        "platform": normalize_platform(platform or payload.get("platform")),
        "recordType": normalize_text(record_type) or "article",
        "author": author or "unknown",
        "title": title or "untitled",
        "url": url,
        "publishedAt": published_at or None,
        "metrics": normalize_metrics(payload),
        "content": {
            "summary": summary,
            "rawTextPath": normalize_text(payload.get("rawTextPath")) or None,
        },
        "meta": {
            "topic": normalize_text(payload.get("topic")) or "unclassified",
            "tags": tags,
            "captureMethod": capture_method,
            "sourceFields": {
                "author": author,
                "publishedAt": published_at,
            },
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Re-run the contract tests**

Run:

```powershell
python -m unittest tests.scripts.test_web_scraper_contracts -v
```

Expected: PASS for all three tests.

- [ ] **Step 5: Commit the contract layer**

```bash
git add tests/scripts/test_web_scraper_contracts.py scripts/web_scraper_contracts.py
git commit -m "feat: add web scraper normalization contract"
```

### Task 2: Add Adapter Dispatch and Local Providers

**Files:**
- Create: `tests/scripts/test_web_scraper_mcp.py`
- Create: `scripts/web_scraper_mcp.py`
- Create: `config/web_scraper_mcp.json`

- [ ] **Step 1: Write the failing adapter tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.web_scraper_mcp import run_request


class WebScraperMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.fixture_dir = self.root / "fixtures"
        self.fixture_dir.mkdir(parents=True, exist_ok=True)
        (self.fixture_dir / "zhihu-search.json").write_text(
            json.dumps(
                [
                    {
                        "platform": "zhihu",
                        "title": "AI工具怎么选，先看4个判断",
                        "url": "https://example.com/1",
                        "summary": "摘要1",
                        "views": 100,
                    },
                    {
                        "platform": "zhihu",
                        "title": "别急着换工具，先看结果能不能继续改",
                        "url": "https://example.com/2",
                        "summary": "摘要2",
                        "views": 80,
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.config = {
            "schemaVersion": 1,
            "defaultProvider": "fixture",
            "providers": {
                "fixture": {
                    "type": "fixture",
                    "fixtures": {
                        "search_content:zhihu:AI工具": str(self.fixture_dir / "zhihu-search.json")
                    },
                },
                "import_json": {"type": "import_json"},
            },
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_fixture_provider_returns_normalized_search_rows(self) -> None:
        response = run_request(
            {
                "action": "search_content",
                "platform": "zhihu",
                "query": "AI工具",
                "limit": 1,
            },
            self.config,
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(response["records"]), 1)
        self.assertEqual(response["records"][0]["platform"], "zhihu")

    def test_import_json_provider_normalizes_inline_record(self) -> None:
        response = run_request(
            {
                "action": "normalize_record",
                "provider": "import_json",
                "record": {
                    "platform": "wechat",
                    "title": "AI图片越真实，越要先做4步避坑",
                    "summary": "摘要",
                    "url": "https://example.com/wx",
                },
            },
            self.config,
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["record"]["platform"], "wechat")

    def test_unsupported_action_returns_validation_error(self) -> None:
        response = run_request({"action": "unknown_action"}, self.config)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["errorType"], "validation_error")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm the dispatcher is missing**

Run:

```powershell
python -m unittest tests.scripts.test_web_scraper_mcp -v
```

Expected: FAIL with `ModuleNotFoundError` or missing `run_request`.

- [ ] **Step 3: Add the provider config file**

```json
{
  "schemaVersion": 1,
  "defaultProvider": "import_json",
  "providers": {
    "fixture": {
      "type": "fixture",
      "fixtures": {}
    },
    "import_json": {
      "type": "import_json"
    }
  }
}
```

- [ ] **Step 4: Implement the adapter dispatcher**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.web_scraper_contracts import normalize_record
except ModuleNotFoundError:
    from web_scraper_contracts import normalize_record


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "web_scraper_mcp.json"


SUPPORTED_ACTIONS = {
    "search_content",
    "fetch_article",
    "fetch_author_feed",
    "extract_metrics",
    "normalize_record",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the repo-local web_scraper_mcp adapter.")
    parser.add_argument("request_path", type=Path, help="Path to the adapter request JSON file.")
    parser.add_argument("--output", type=Path, default=None, help="Optional response output path.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Config file path.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_maybe(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def error_response(message: str, error_type: str = "validation_error") -> dict[str, Any]:
    return {
        "status": "error",
        "errorType": error_type,
        "message": message,
    }


def fixture_key(request: dict[str, Any]) -> str:
    return f"{request.get('action')}:{request.get('platform', '')}:{request.get('query', '')}"


def load_fixture_rows(provider_config: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    fixtures = provider_config.get("fixtures", {})
    path = fixtures.get(fixture_key(request))
    if not path:
        raise ValueError(f"missing fixture for {fixture_key(request)}")
    payload = read_json_maybe(Path(path))
    if not isinstance(payload, list):
        raise ValueError("fixture payload must be a list")
    return payload


def import_rows_from_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(request.get("record"), dict):
        return [request["record"]]
    input_path = request.get("inputPath")
    if not input_path:
        raise ValueError("import_json provider requires record or inputPath")
    payload = read_json_maybe(Path(input_path))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("input payload must be a dict or list")


def normalize_rows(rows: list[dict[str, Any]], request: dict[str, Any], provider_type: str) -> list[dict[str, Any]]:
    return [
        normalize_record(
            row,
            platform=request.get("platform"),
            record_type=request.get("recordType", "article"),
            capture_method=provider_type,
        )
        for row in rows
    ]


def run_request(request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    if action not in SUPPORTED_ACTIONS:
        return error_response(f"unsupported action: {action}")

    provider_name = request.get("provider") or config.get("defaultProvider") or "import_json"
    provider_config = (config.get("providers") or {}).get(provider_name, {})
    provider_type = provider_config.get("type")
    if provider_type not in {"fixture", "import_json"}:
        return error_response(f"unsupported provider: {provider_name}")

    try:
        rows = (
            load_fixture_rows(provider_config, request)
            if provider_type == "fixture"
            else import_rows_from_request(request)
        )
        normalized = normalize_rows(rows, request, provider_type)
    except ValueError as exc:
        return error_response(str(exc))

    if action == "search_content":
        limit = max(1, int(request.get("limit", len(normalized)) or len(normalized)))
        return {"status": "ok", "records": normalized[:limit]}
    if action == "fetch_author_feed":
        return {"status": "ok", "records": normalized}
    if action == "extract_metrics":
        first = normalized[0]
        return {"status": "ok", "metrics": first["metrics"], "record": first}
    if action == "fetch_article":
        return {"status": "ok", "record": normalized[0]}
    return {"status": "ok", "record": normalized[0]}


def main() -> int:
    args = parse_args()
    request = read_json(args.request_path)
    config = read_json(args.config)
    response = run_request(request, config)
    text = json.dumps(response, ensure_ascii=False, indent=2)
    if args.output:
        write_json(args.output, response)
    print(text)
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Re-run the adapter tests**

Run:

```powershell
python -m unittest tests.scripts.test_web_scraper_mcp -v
```

Expected: PASS for all three adapter tests.

- [ ] **Step 6: Commit the adapter layer**

```bash
git add config/web_scraper_mcp.json tests/scripts/test_web_scraper_mcp.py scripts/web_scraper_mcp.py
git commit -m "feat: add web scraper adapter dispatcher"
```

### Task 3: Add Benchmark Monitor Artifact Generation

**Files:**
- Create: `tests/scripts/test_run_benchmark_monitor.py`
- Create: `scripts/run_benchmark_monitor.py`

- [ ] **Step 1: Write the failing benchmark monitor tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_benchmark_monitor import run_benchmark_monitor


class RunBenchmarkMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.records_path = self.root / "records.jsonl"
        self.output_dir = self.root / "generated" / "demo-slug"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        rows = [
            {
                "platform": "zhihu",
                "recordType": "article",
                "author": "A",
                "title": "AI工具怎么选，先看4个判断",
                "url": "https://example.com/1",
                "publishedAt": "2026-06-14T08:30:00+08:00",
                "metrics": {"views": 1200, "likes": 23, "comments": 4, "favorites": 5, "shares": 0},
                "content": {"summary": "摘要1", "rawTextPath": None},
                "meta": {"topic": "AI工具", "tags": ["AI工具"], "captureMethod": "fixture"},
            },
            {
                "platform": "wechat",
                "recordType": "article",
                "author": "B",
                "title": "AI图片越真实，越要先做4步避坑",
                "url": "https://example.com/2",
                "publishedAt": "2026-06-14T09:30:00+08:00",
                "metrics": {"views": 600, "likes": 16, "comments": 2, "favorites": 3, "shares": 0},
                "content": {"summary": "摘要2", "rawTextPath": None},
                "meta": {"topic": "AI工具", "tags": ["AI图片"], "captureMethod": "fixture"},
            },
        ]
        with self.records_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_benchmark_monitor_writes_jsonl_and_markdown(self) -> None:
        result = run_benchmark_monitor(self.records_path, self.output_dir, slug="demo-slug")
        self.assertTrue((self.output_dir / "benchmark-records.jsonl").exists())
        self.assertTrue((self.output_dir / "benchmark-monitor.md").exists())
        self.assertEqual(result["recordCount"], 2)

    def test_run_benchmark_monitor_markdown_mentions_platforms_and_titles(self) -> None:
        run_benchmark_monitor(self.records_path, self.output_dir, slug="demo-slug")
        content = (self.output_dir / "benchmark-monitor.md").read_text(encoding="utf-8")
        self.assertIn("zhihu", content)
        self.assertIn("wechat", content)
        self.assertIn("AI工具怎么选", content)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm the monitor script is missing**

Run:

```powershell
python -m unittest tests.scripts.test_run_benchmark_monitor -v
```

Expected: FAIL with `ModuleNotFoundError` for `scripts.run_benchmark_monitor`.

- [ ] **Step 3: Implement benchmark artifact generation**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.web_scraper_contracts import write_jsonl
except ModuleNotFoundError:
    from web_scraper_contracts import write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build benchmark monitor artifacts from normalized records.")
    parser.add_argument("records_path", type=Path, help="Normalized JSONL records path.")
    parser.add_argument("output_dir", type=Path, help="Generated output directory.")
    parser.add_argument("--slug", required=True, help="Content slug.")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def build_markdown(rows: list[dict[str, Any]], slug: str) -> str:
    lines = [
        "# Benchmark Monitor",
        "",
        f"- Slug: `{slug}`",
        f"- Record count: `{len(rows)}`",
        "",
        "## Platform Summary",
        "",
    ]

    by_platform: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_platform.setdefault(row["platform"], []).append(row)

    for platform, items in sorted(by_platform.items()):
        avg_views = sum(item["metrics"]["views"] for item in items) / max(len(items), 1)
        lines.append(f"- {platform}: `{len(items)}` records, avg views `{avg_views:.0f}`")

    lines.extend(["", "## Sample Records", ""])
    ranked = sorted(rows, key=lambda item: item["metrics"]["views"], reverse=True)
    for row in ranked[:10]:
        lines.append(
            "- "
            f"{row['platform']} | {row['author']} | `{row['metrics']['views']}` views | "
            f"{row['title']}"
        )
    return "\n".join(lines).strip() + "\n"


def run_benchmark_monitor(records_path: Path, output_dir: Path, *, slug: str) -> dict[str, Any]:
    rows = read_jsonl(records_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_copy = output_dir / "benchmark-records.jsonl"
    markdown_path = output_dir / "benchmark-monitor.md"

    write_jsonl(normalized_copy, rows)
    markdown_path.write_text(build_markdown(rows, slug), encoding="utf-8")

    return {
        "slug": slug,
        "recordCount": len(rows),
        "recordsPath": str(normalized_copy),
        "markdownPath": str(markdown_path),
    }


def main() -> int:
    args = parse_args()
    result = run_benchmark_monitor(args.records_path, args.output_dir, slug=args.slug)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Re-run the benchmark monitor tests**

Run:

```powershell
python -m unittest tests.scripts.test_run_benchmark_monitor -v
```

Expected: PASS for both benchmark monitor tests.

- [ ] **Step 5: Commit the monitor artifact generator**

```bash
git add tests/scripts/test_run_benchmark_monitor.py scripts/run_benchmark_monitor.py
git commit -m "feat: add benchmark monitor artifact generator"
```

### Task 4: Register the Adapter in the v3 Tool Registry

**Files:**
- Modify: `config/tool_registry.json`

- [ ] **Step 1: Add the adapter to the tool registry**

Update the `web_scraper_mcp` entry to this shape:

```json
"web_scraper_mcp": {
  "mode": "local_script",
  "status": "active",
  "primary": "scripts/web_scraper_mcp.py",
  "fallbacks": [
    "scripts/run_benchmark_monitor.py"
  ],
  "providerConfig": "config/web_scraper_mcp.json",
  "purpose": "统一网页采集与结构化记录入口"
}
```

- [ ] **Step 2: Verify the registry still parses**

Run:

```powershell
python -X utf8 -c "import json, pathlib; print(json.loads(pathlib.Path('config/tool_registry.json').read_text(encoding='utf-8'))['interfaces']['web_scraper_mcp']['status'])"
```

Expected output:

```text
active
```

- [ ] **Step 3: Commit the registry change**

```bash
git add config/tool_registry.json
git commit -m "chore: register web scraper adapter in tool registry"
```

### Task 5: Full Verification and Example Run

**Files:**
- Verify only

- [ ] **Step 1: Run the focused adapter test suite**

Run:

```powershell
python -m unittest tests.scripts.test_web_scraper_contracts tests.scripts.test_web_scraper_mcp tests.scripts.test_run_benchmark_monitor -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run the full repository test suite**

Run:

```powershell
python -m unittest discover -s tests -t . -v
```

Expected: full test suite PASS with the new adapter included.

- [ ] **Step 3: Run one example request through the adapter**

Prepare request file:

```json
{
  "action": "normalize_record",
  "provider": "import_json",
  "record": {
    "platform": "zhihu",
    "title": "设计工具怎么选，先看4个判断",
    "summary": "先看结果能不能继续改，再看工具值不值得长期用。",
    "url": "https://example.com/post",
    "author": "示例作者",
    "views": 1200,
    "likes": 23
  }
}
```

Run:

```powershell
python scripts/web_scraper_mcp.py .tmp\requests\web-scraper-normalize.json --output .tmp\responses\web-scraper-normalize.json
```

Expected: exit code `0` and `.tmp\responses\web-scraper-normalize.json` exists with `"status": "ok"`.

- [ ] **Step 4: Build one benchmark monitor artifact pair**

Run:

```powershell
python scripts/run_benchmark_monitor.py .tmp\sample-benchmark\records.jsonl .tmp\generated\demo-slug --slug demo-slug
```

Expected: `.tmp\generated\demo-slug\benchmark-records.jsonl` and `.tmp\generated\demo-slug\benchmark-monitor.md` both exist.

- [ ] **Step 5: Commit the verified adapter milestone**

```bash
git add config/web_scraper_mcp.json config/tool_registry.json scripts/web_scraper_contracts.py scripts/web_scraper_mcp.py scripts/run_benchmark_monitor.py tests/scripts/test_web_scraper_contracts.py tests/scripts/test_web_scraper_mcp.py tests/scripts/test_run_benchmark_monitor.py
git commit -m "feat: add repo-local web scraper adapter foundation"
```
