# Codex API MCP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repo-local `codex_api_mcp` adapter that validates generation requests, supports deterministic local providers, and writes stable article-generation artifacts into each content slug directory.

**Architecture:** Keep request/response validation in one focused contract module and the adapter runner in a separate script, following the repo's flat `scripts/` layout. Implement two providers in this phase: `fixture` for deterministic tests and `packet` for live-workflow handoff without lying about a connected external AI backend. Add one generation job wrapper that reads existing benchmark/analysis inputs, calls the adapter, and writes `article.md`, `title-variants.json`, and `ai-summary.json` to a generated slug directory.

**Tech Stack:** Python 3 standard library, JSON files, `unittest`, existing generated artifact layout under `.tmp/generated/<slug>/`

---

### File Structure

**Create:**
- `config/codex_api_mcp.json`
- `scripts/codex_api_contracts.py`
- `scripts/codex_api_mcp.py`
- `scripts/run_codex_generation_job.py`
- `tests/scripts/test_codex_api_contracts.py`
- `tests/scripts/test_codex_api_mcp.py`
- `tests/scripts/test_run_codex_generation_job.py`

**Modify:**
- `config/tool_registry.json`

**Do not modify in this plan:**
- `scripts/run_v3_content_ops.py`
- formal publish scripts
- external SDK dependency files

### Task 1: Add Contract Tests for AI Request and Response Shapes

**Files:**
- Create: `tests/scripts/test_codex_api_contracts.py`
- Create: `scripts/codex_api_contracts.py`

- [ ] **Step 1: Write the failing contract tests**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.codex_api_contracts import (
    build_artifact_paths,
    validate_request,
    validate_success_payload,
)


class CodexApiContractsTests(unittest.TestCase):
    def test_validate_request_accepts_required_generation_fields(self) -> None:
        request = {
            "action": "draft_article",
            "requestId": "req-001",
            "topic": "设计工具怎么选",
            "platforms": ["toutiao", "zhihu", "wechat"],
            "contentDomain": "AI工具",
            "outputDir": "C:/tmp/generated/demo-slug",
        }
        validated = validate_request(request)
        self.assertEqual(validated["action"], "draft_article")
        self.assertEqual(validated["platforms"], ["toutiao", "zhihu", "wechat"])

    def test_validate_request_rejects_missing_output_dir(self) -> None:
        request = {
            "action": "draft_article",
            "requestId": "req-002",
            "topic": "设计工具怎么选",
        }
        with self.assertRaises(ValueError):
            validate_request(request)

    def test_build_artifact_paths_uses_generated_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = build_artifact_paths(Path(temp_dir))
            self.assertEqual(paths["articlePath"].name, "article.md")
            self.assertEqual(paths["titleVariantsPath"].name, "title-variants.json")
            self.assertEqual(paths["summaryPath"].name, "ai-summary.json")

    def test_validate_success_payload_requires_written_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            article = output_dir / "article.md"
            titles = output_dir / "title-variants.json"
            summary = output_dir / "ai-summary.json"
            article.write_text("# Demo\\n", encoding="utf-8")
            titles.write_text("{}", encoding="utf-8")
            summary.write_text("{}", encoding="utf-8")

            payload = {
                "requestId": "req-003",
                "status": "ok",
                "provider": "fixture",
                "artifacts": {
                    "articlePath": str(article),
                    "titleVariantsPath": str(titles),
                    "summaryPath": str(summary),
                },
                "usage": {"inputTokens": 0, "outputTokens": 0},
                "warnings": [],
            }
            validated = validate_success_payload(payload)
            self.assertEqual(validated["status"], "ok")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm the contract module is missing**

Run:

```powershell
python -m unittest tests.scripts.test_codex_api_contracts -v
```

Expected: FAIL with `ModuleNotFoundError` for `scripts.codex_api_contracts`.

- [ ] **Step 3: Implement the request/response contract helpers**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


SUPPORTED_ACTIONS = {
    "draft_article",
    "generate_titles",
    "build_rewrite_plan",
    "humanize_article",
    "summarize_quality_issues",
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def validate_request(request: dict[str, Any]) -> dict[str, Any]:
    action = normalize_text(request.get("action"))
    request_id = normalize_text(request.get("requestId"))
    topic = normalize_text(request.get("topic"))
    output_dir = normalize_text(request.get("outputDir"))

    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported action: {action}")
    if not request_id:
        raise ValueError("requestId is required")
    if not topic:
        raise ValueError("topic is required")
    if not output_dir:
        raise ValueError("outputDir is required")

    platforms = [normalize_text(item) for item in request.get("platforms", []) if normalize_text(item)]
    if not platforms:
        raise ValueError("at least one platform is required")

    return {
        **request,
        "action": action,
        "requestId": request_id,
        "topic": topic,
        "platforms": platforms,
        "contentDomain": normalize_text(request.get("contentDomain")) or "unclassified",
        "outputDir": output_dir,
    }


def build_artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "articlePath": output_dir / "article.md",
        "titleVariantsPath": output_dir / "title-variants.json",
        "summaryPath": output_dir / "ai-summary.json",
    }


def validate_success_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != "ok":
        raise ValueError("success payload must have status ok")

    artifacts = payload.get("artifacts") or {}
    required = ("articlePath", "titleVariantsPath", "summaryPath")
    for key in required:
        path = artifacts.get(key)
        if not path:
            raise ValueError(f"missing artifact path: {key}")
        if not Path(path).exists():
            raise ValueError(f"artifact path does not exist: {path}")

    usage = payload.get("usage") or {}
    if "inputTokens" not in usage or "outputTokens" not in usage:
        raise ValueError("usage must contain inputTokens and outputTokens")

    return payload
```

- [ ] **Step 4: Re-run the contract tests**

Run:

```powershell
python -m unittest tests.scripts.test_codex_api_contracts -v
```

Expected: PASS for all four tests.

- [ ] **Step 5: Commit the contract layer**

```bash
git add tests/scripts/test_codex_api_contracts.py scripts/codex_api_contracts.py
git commit -m "feat: add codex api contract helpers"
```

### Task 2: Add Adapter Dispatch for Fixture and Packet Providers

**Files:**
- Create: `tests/scripts/test_codex_api_mcp.py`
- Create: `scripts/codex_api_mcp.py`
- Create: `config/codex_api_mcp.json`

- [ ] **Step 1: Write the failing adapter tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.codex_api_mcp import run_request


class CodexApiMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.fixture_dir = self.root / "fixtures"
        self.fixture_dir.mkdir(parents=True, exist_ok=True)
        (self.fixture_dir / "draft-article.json").write_text(
            json.dumps(
                {
                    "article_markdown": "# 设计工具怎么选\n\n先看结果能不能继续改。",
                    "title_variants": {
                        "toutiao": ["设计工具怎么选，先看4个判断"],
                        "zhihu": ["设计工具怎么选，哪些判断最值钱"],
                        "wechat": ["设计工具怎么选，我现在先看能不能继续改"]
                    },
                    "summary": {
                        "hook": "先看结果，再谈工具。",
                        "angle": "减少返工",
                        "warnings": []
                    },
                    "usage": {"inputTokens": 1200, "outputTokens": 800}
                },
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
                        "draft_article": str(self.fixture_dir / "draft-article.json")
                    },
                },
                "packet": {
                    "type": "packet",
                    "packetDirName": "ai-packets"
                },
            },
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_fixture_provider_writes_generation_artifacts(self) -> None:
        output_dir = self.root / "generated" / "demo-slug"
        response = run_request(
            {
                "action": "draft_article",
                "requestId": "req-001",
                "topic": "设计工具怎么选",
                "platforms": ["toutiao", "zhihu", "wechat"],
                "contentDomain": "AI工具",
                "outputDir": str(output_dir),
            },
            self.config,
        )
        self.assertEqual(response["status"], "ok")
        self.assertTrue((output_dir / "article.md").exists())
        self.assertTrue((output_dir / "title-variants.json").exists())
        self.assertTrue((output_dir / "ai-summary.json").exists())

    def test_packet_provider_writes_request_packet_and_returns_packet_status(self) -> None:
        output_dir = self.root / "generated" / "demo-slug"
        response = run_request(
            {
                "action": "draft_article",
                "provider": "packet",
                "requestId": "req-002",
                "topic": "设计工具怎么选",
                "platforms": ["toutiao"],
                "contentDomain": "AI工具",
                "outputDir": str(output_dir),
            },
            self.config,
        )
        self.assertEqual(response["status"], "queued")
        self.assertTrue((output_dir / "ai-packets" / "req-002.json").exists())

    def test_unsupported_provider_returns_validation_error(self) -> None:
        output_dir = self.root / "generated" / "demo-slug"
        response = run_request(
            {
                "action": "draft_article",
                "provider": "missing",
                "requestId": "req-003",
                "topic": "设计工具怎么选",
                "platforms": ["wechat"],
                "outputDir": str(output_dir),
            },
            self.config,
        )
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["errorType"], "validation_error")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm the adapter is missing**

Run:

```powershell
python -m unittest tests.scripts.test_codex_api_mcp -v
```

Expected: FAIL with `ModuleNotFoundError` for `scripts.codex_api_mcp`.

- [ ] **Step 3: Add the provider config**

```json
{
  "schemaVersion": 1,
  "defaultProvider": "packet",
  "providers": {
    "fixture": {
      "type": "fixture",
      "fixtures": {}
    },
    "packet": {
      "type": "packet",
      "packetDirName": "ai-packets"
    }
  }
}
```

- [ ] **Step 4: Implement the adapter runner**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.codex_api_contracts import build_artifact_paths, validate_request, validate_success_payload
except ModuleNotFoundError:
    from codex_api_contracts import build_artifact_paths, validate_request, validate_success_payload


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "codex_api_mcp.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the repo-local codex_api_mcp adapter.")
    parser.add_argument("request_path", type=Path, help="Path to adapter request JSON.")
    parser.add_argument("--output", type=Path, default=None, help="Optional adapter response path.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Provider config path.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def error_response(message: str, error_type: str = "validation_error") -> dict[str, Any]:
    return {
        "status": "error",
        "errorType": error_type,
        "message": message,
        "retryable": False,
    }


def write_generation_artifacts(output_dir: Path, payload: dict[str, Any]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = build_artifact_paths(output_dir)
    paths["articlePath"].write_text(payload["article_markdown"], encoding="utf-8")
    paths["titleVariantsPath"].write_text(
        json.dumps(payload["title_variants"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["summaryPath"].write_text(
        json.dumps(payload["summary"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {key: str(value) for key, value in paths.items()}


def run_fixture_provider(request: dict[str, Any], provider_config: dict[str, Any]) -> dict[str, Any]:
    fixture_path = (provider_config.get("fixtures") or {}).get(request["action"])
    if not fixture_path:
        raise ValueError(f"missing fixture for action {request['action']}")
    payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    artifacts = write_generation_artifacts(Path(request["outputDir"]), payload)
    response = {
        "requestId": request["requestId"],
        "status": "ok",
        "provider": "fixture",
        "artifacts": artifacts,
        "usage": payload.get("usage", {"inputTokens": 0, "outputTokens": 0}),
        "warnings": payload.get("summary", {}).get("warnings", []),
    }
    return validate_success_payload(response)


def run_packet_provider(request: dict[str, Any], provider_config: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(request["outputDir"])
    packet_dir = output_dir / str(provider_config.get("packetDirName") or "ai-packets")
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_path = packet_dir / f"{request['requestId']}.json"
    packet_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "requestId": request["requestId"],
        "status": "queued",
        "provider": "packet",
        "packetPath": str(packet_path),
        "message": "request packet written for later fulfillment",
    }


def run_request(request_payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    try:
        request = validate_request(request_payload)
    except ValueError as exc:
        return error_response(str(exc))

    provider_name = request_payload.get("provider") or config.get("defaultProvider") or "packet"
    provider_config = (config.get("providers") or {}).get(provider_name, {})
    provider_type = provider_config.get("type")

    try:
        if provider_type == "fixture":
            return run_fixture_provider(request, provider_config)
        if provider_type == "packet":
            return run_packet_provider(request, provider_config)
    except ValueError as exc:
        return error_response(str(exc))

    return error_response(f"unsupported provider: {provider_name}")


def main() -> int:
    args = parse_args()
    request = read_json(args.request_path)
    config = read_json(args.config)
    response = run_request(request, config)
    if args.output:
        write_json(args.output, response)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") in {"ok", "queued"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Re-run the adapter tests**

Run:

```powershell
python -m unittest tests.scripts.test_codex_api_mcp -v
```

Expected: PASS for all three adapter tests.

- [ ] **Step 6: Commit the adapter dispatcher**

```bash
git add config/codex_api_mcp.json tests/scripts/test_codex_api_mcp.py scripts/codex_api_mcp.py
git commit -m "feat: add codex api adapter dispatcher"
```

### Task 3: Add a Generation Job Wrapper for Slug Directories

**Files:**
- Create: `tests/scripts/test_run_codex_generation_job.py`
- Create: `scripts/run_codex_generation_job.py`

- [ ] **Step 1: Write the failing generation job tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_codex_generation_job import run_generation_job


class RunCodexGenerationJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.generated_dir = self.root / ".tmp" / "generated" / "demo-slug"
        self.generated_dir.mkdir(parents=True, exist_ok=True)

        (self.generated_dir / "benchmark-monitor.md").write_text("# Benchmark\\n", encoding="utf-8")
        (self.generated_dir / "viral-analysis.md").write_text("# Viral\\n", encoding="utf-8")
        (self.generated_dir / "rewrite-plan.md").write_text("# Rewrite\\n", encoding="utf-8")

        self.config = {
            "schemaVersion": 1,
            "defaultProvider": "fixture",
            "providers": {
                "fixture": {
                    "type": "fixture",
                    "fixtures": {}
                }
            }
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_generation_job_builds_request_and_writes_request_copy(self) -> None:
        request_path = self.generated_dir / "generation-request.json"
        result = run_generation_job(
            generated_dir=self.generated_dir,
            topic="设计工具怎么选",
            content_domain="AI工具",
            platforms=["toutiao", "zhihu", "wechat"],
            provider="packet",
            config={"schemaVersion": 1, "defaultProvider": "packet", "providers": {"packet": {"type": "packet", "packetDirName": "ai-packets"}}},
            request_path=request_path,
        )
        self.assertTrue(request_path.exists())
        self.assertEqual(result["status"], "queued")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm the job script is missing**

Run:

```powershell
python -m unittest tests.scripts.test_run_codex_generation_job -v
```

Expected: FAIL with `ModuleNotFoundError` for `scripts.run_codex_generation_job`.

- [ ] **Step 3: Implement the generation job wrapper**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.codex_api_mcp import run_request
except ModuleNotFoundError:
    from codex_api_mcp import run_request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "codex_api_mcp.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one codex_api_mcp generation job for a slug directory.")
    parser.add_argument("generated_dir", type=Path, help="Generated slug directory.")
    parser.add_argument("--topic", required=True, help="Article topic.")
    parser.add_argument("--content-domain", required=True, help="Content domain id.")
    parser.add_argument("--provider", default=None, help="Optional provider override.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Provider config file.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_request(
    *,
    generated_dir: Path,
    topic: str,
    content_domain: str,
    platforms: list[str],
    provider: str | None,
) -> dict[str, Any]:
    slug = generated_dir.name
    request = {
        "action": "draft_article",
        "requestId": f"{slug}-draft-article",
        "topic": topic,
        "platforms": platforms,
        "contentDomain": content_domain,
        "outputDir": str(generated_dir),
        "inputs": {
            "benchmarkSummaryPath": str(generated_dir / "benchmark-monitor.md"),
            "viralAnalysisPath": str(generated_dir / "viral-analysis.md"),
            "rewritePlanPath": str(generated_dir / "rewrite-plan.md"),
        },
    }
    if provider:
        request["provider"] = provider
    return request


def run_generation_job(
    *,
    generated_dir: Path,
    topic: str,
    content_domain: str,
    platforms: list[str],
    provider: str | None,
    config: dict[str, Any],
    request_path: Path,
) -> dict[str, Any]:
    request = build_request(
        generated_dir=generated_dir,
        topic=topic,
        content_domain=content_domain,
        platforms=platforms,
        provider=provider,
    )
    write_json(request_path, request)
    return run_request(request, config)


def main() -> int:
    args = parse_args()
    generated_dir = args.generated_dir.resolve()
    config = read_json(args.config)
    request_path = generated_dir / "generation-request.json"
    response = run_generation_job(
        generated_dir=generated_dir,
        topic=args.topic,
        content_domain=args.content_domain,
        platforms=["toutiao", "zhihu", "wechat"],
        provider=args.provider,
        config=config,
        request_path=request_path,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") in {"ok", "queued"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Re-run the generation job tests**

Run:

```powershell
python -m unittest tests.scripts.test_run_codex_generation_job -v
```

Expected: PASS for the generation job test.

- [ ] **Step 5: Commit the generation wrapper**

```bash
git add tests/scripts/test_run_codex_generation_job.py scripts/run_codex_generation_job.py
git commit -m "feat: add codex generation job wrapper"
```

### Task 4: Register the Adapter in the v3 Tool Registry

**Files:**
- Modify: `config/tool_registry.json`

- [ ] **Step 1: Update the `codex_api_mcp` entry**

Change the registry entry to:

```json
"codex_api_mcp": {
  "mode": "local_script",
  "status": "active",
  "primary": "scripts/codex_api_mcp.py",
  "fallbacks": [
    "scripts/run_codex_generation_job.py"
  ],
  "providerConfig": "config/codex_api_mcp.json",
  "purpose": "统一 AI 生成入口"
}
```

- [ ] **Step 2: Verify the registry still parses**

Run:

```powershell
python -X utf8 -c "import json, pathlib; print(json.loads(pathlib.Path('config/tool_registry.json').read_text(encoding='utf-8'))['interfaces']['codex_api_mcp']['status'])"
```

Expected output:

```text
active
```

- [ ] **Step 3: Commit the registry change**

```bash
git add config/tool_registry.json
git commit -m "chore: register codex api adapter in tool registry"
```

### Task 5: Full Verification and Example Runs

**Files:**
- Verify only

- [ ] **Step 1: Run the focused adapter test suite**

Run:

```powershell
python -m unittest tests.scripts.test_codex_api_contracts tests.scripts.test_codex_api_mcp tests.scripts.test_run_codex_generation_job -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run the full repository test suite**

Run:

```powershell
python -m unittest discover -s tests -t . -v
```

Expected: full test suite PASS with the new adapter included.

- [ ] **Step 3: Run one packet-mode generation job**

Run:

```powershell
python scripts/run_codex_generation_job.py .tmp\generated\demo-slug --topic "设计工具怎么选" --content-domain "AI工具" --provider packet
```

Expected: exit code `0`, `.tmp\generated\demo-slug\generation-request.json` exists, and `.tmp\generated\demo-slug\ai-packets\demo-slug-draft-article.json` exists.

- [ ] **Step 4: Run one fixture-mode generation job**

Prepare `config/codex_api_mcp.json` fixture mapping for `draft_article`, then run:

```powershell
python scripts/run_codex_generation_job.py .tmp\generated\demo-slug --topic "设计工具怎么选" --content-domain "AI工具" --provider fixture
```

Expected: exit code `0`, plus these files exist:

- `.tmp\generated\demo-slug\article.md`
- `.tmp\generated\demo-slug\title-variants.json`
- `.tmp\generated\demo-slug\ai-summary.json`

- [ ] **Step 5: Commit the verified adapter milestone**

```bash
git add config/codex_api_mcp.json config/tool_registry.json scripts/codex_api_contracts.py scripts/codex_api_mcp.py scripts/run_codex_generation_job.py tests/scripts/test_codex_api_contracts.py tests/scripts/test_codex_api_mcp.py tests/scripts/test_run_codex_generation_job.py
git commit -m "feat: add repo-local codex api adapter foundation"
```
