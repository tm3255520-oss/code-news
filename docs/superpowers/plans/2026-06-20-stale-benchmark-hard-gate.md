# Stale Benchmark Hard Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block Toutiao, Zhihu, and WeChat prepublish when benchmark inputs are stale, and surface the same block reason in pipeline state, publish preview, and operator checklist.

**Architecture:** Keep freshness detection in `scripts/run_content_signal_pipeline.py` unchanged and apply the new hard gate only inside `scripts/run_v3_content_ops.py`, where platform state, publish preview, and checklist are already composed. Extend the existing prepublish status flow rather than adding a parallel gate system.

**Tech Stack:** Python 3, `unittest`, JSON state files under `.tmp/generated/<slug>/`

---

## File Structure

- Modify: `C:\Users\Administrator\Documents\code-news\scripts\run_v3_content_ops.py`
  - Owns prepublish state composition, `publish-preview.json`, and `operator-checklist.md`
- Modify: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_v3_content_ops.py`
  - Owns regression coverage for v3 prepublish behavior
- Reference only: `C:\Users\Administrator\Documents\code-news\docs\superpowers\specs\2026-06-20-stale-benchmark-hard-gate-design.md`
  - Approved design source for this change

## Task 1: Add a failing stale-input regression

**Files:**
- Modify: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_v3_content_ops.py`
- Reference: `C:\Users\Administrator\Documents\code-news\scripts\run_v3_content_ops.py`

- [ ] **Step 1: Write the failing test**

Add a new test near the existing signal-pipeline cases:

```python
    def test_run_v3_prepublish_blocks_when_benchmark_inputs_are_stale(self) -> None:
        records_path = self.generated_dir / "benchmark-records.jsonl"
        records = [
            {
                "platform": "toutiao",
                "recordType": "article",
                "author": "Flow Lab",
                "title": "Ultimate workflow: publish without rework",
                "url": "https://example.com/toutiao-1",
                "publishedAt": "2026-06-14T08:30:00+08:00",
                "metrics": {"views": 1800, "likes": 55, "comments": 12, "favorites": 9, "shares": 5},
                "content": {"summary": "Auto publishing workflow for content teams.", "rawTextPath": None},
                "meta": {"topic": "ai_tools", "tags": ["workflow", "publish"], "captureMethod": "fixture"},
            }
        ]
        with records_path.open("w", encoding="utf-8") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        old_timestamp = 1760800000
        os.utime(records_path, (old_timestamp, old_timestamp))

        run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )

        preview = json.loads((self.generated_dir / "publish-preview.json").read_text(encoding="utf-8"))
        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        checklist = (self.generated_dir / "operator-checklist.md").read_text(encoding="utf-8")

        self.assertEqual(state["v3"]["signalPipeline"]["freshnessStatus"], "stale")
        self.assertEqual(preview["platforms"]["toutiao"]["status"], "blocked_by_stale_benchmark_inputs")
        self.assertEqual(preview["platforms"]["zhihu"]["status"], "blocked_by_stale_benchmark_inputs")
        self.assertEqual(preview["platforms"]["wechat"]["status"], "blocked_by_stale_benchmark_inputs")
        self.assertEqual(state["platforms"]["toutiao"]["prepublishStatus"], "blocked_by_stale_benchmark_inputs")
        self.assertEqual(state["platforms"]["zhihu"]["prepublishStatus"], "blocked_by_stale_benchmark_inputs")
        self.assertEqual(state["platforms"]["wechat"]["prepublishStatus"], "blocked_by_stale_benchmark_inputs")
        self.assertIn("stale", checklist)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.scripts.test_run_v3_content_ops.RunV3ContentOpsTests.test_run_v3_prepublish_blocks_when_benchmark_inputs_are_stale -v
```

Expected: FAIL because `publish-preview` and `prepublishStatus` still resolve to the current non-stale statuses.

- [ ] **Step 3: Commit the failing-test checkpoint**

Run:

```powershell
git add tests/scripts/test_run_v3_content_ops.py
git commit -m "test: cover stale benchmark hard gate"
```

Expected: a commit containing only the new failing regression.

## Task 2: Implement the stale hard gate in prepublish preview

**Files:**
- Modify: `C:\Users\Administrator\Documents\code-news\scripts\run_v3_content_ops.py`
- Test: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_v3_content_ops.py`

- [ ] **Step 1: Add a helper that resolves stale blocking status**

Insert a focused helper near `evaluate_asset_gate()`:

```python
def resolve_stale_benchmark_block(signal_pipeline: dict[str, Any]) -> dict[str, Any] | None:
    if str(signal_pipeline.get("freshnessStatus") or "") != "stale":
        return None
    return {
        "status": "blocked_by_stale_benchmark_inputs",
        "reason": "benchmark_inputs_stale",
        "freshnessStatus": str(signal_pipeline.get("freshnessStatus") or "unknown"),
        "requestAgeHours": signal_pipeline.get("requestAgeHours"),
        "recordsAgeHours": signal_pipeline.get("recordsAgeHours"),
    }
```

- [ ] **Step 2: Thread the new helper into publish-preview generation**

Change `build_publish_preview()` so it receives `signal_pipeline` and prefers the stale block before quality and asset gates:

```python
def build_publish_preview(
    *,
    payload: dict[str, Any],
    state_path: Path,
    preflight: dict[str, Any],
    registry: dict[str, Any],
    asset_gate: dict[str, Any],
    signal_pipeline: dict[str, Any],
) -> dict[str, Any]:
    interfaces = registry.get("interfaces", {})
    publisher = interfaces.get("publisher_skill", {})
    xhs_placeholder = interfaces.get("xhs_placeholder_publish", {})
    stale_block = resolve_stale_benchmark_block(signal_pipeline)
    gate_status = preflight.get("gate", {}).get("status")
    if stale_block:
        status = stale_block["status"]
    elif gate_status != "passed":
        status = "blocked_by_quality_gate"
    elif asset_gate.get("status") != "passed":
        status = "blocked_by_asset_gate"
    else:
        status = "manual_confirmation_required"
```

Update each of the three platform entries to include the stale metadata when present:

```python
            "toutiao": {
                "status": status,
                "payloadPath": str(preflight["platformPayloads"]["toutiao"]),
                "formalPublishEnabled": False,
                "blockContext": stale_block,
            },
```

Repeat the same `blockContext` field for `zhihu` and `wechat`. Leave `xiaohongshu` logic unchanged.

- [ ] **Step 3: Update the call site**

In `run_v3_prepublish()`, update the call:

```python
    publish_preview = build_publish_preview(
        payload=payload,
        state_path=state_path,
        preflight=preflight,
        registry=registry,
        asset_gate=asset_gate,
        signal_pipeline=signal_pipeline,
    )
```

- [ ] **Step 4: Run the stale regression**

Run:

```powershell
python -m unittest tests.scripts.test_run_v3_content_ops.RunV3ContentOpsTests.test_run_v3_prepublish_blocks_when_benchmark_inputs_are_stale -v
```

Expected: still FAIL, but now later in the assertions because pipeline state and checklist are not yet aligned.

- [ ] **Step 5: Commit the preview-gate checkpoint**

Run:

```powershell
git add scripts/run_v3_content_ops.py tests/scripts/test_run_v3_content_ops.py
git commit -m "feat: block publish preview on stale benchmark inputs"
```

Expected: commit records only the preview-layer gate work.

## Task 3: Apply the same stale hard gate to pipeline state and checklist

**Files:**
- Modify: `C:\Users\Administrator\Documents\code-news\scripts\run_v3_content_ops.py`
- Test: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_v3_content_ops.py`

- [ ] **Step 1: Add a helper for platform prepublish status**

Add a second small helper near `resolve_stale_benchmark_block()`:

```python
def resolve_prepublish_status(
    *,
    preflight: dict[str, Any],
    asset_gate: dict[str, Any],
    signal_pipeline: dict[str, Any],
) -> str:
    stale_block = resolve_stale_benchmark_block(signal_pipeline)
    if stale_block:
        return str(stale_block["status"])
    gate_status = preflight.get("gate", {}).get("status")
    if gate_status != "passed":
        return "blocked_by_quality_gate"
    if asset_gate.get("status") != "passed":
        return "blocked_by_asset_gate"
    return "ready_for_confirmation"
```

- [ ] **Step 2: Use the helper when writing platform state**

Replace the inline `ready_for_confirmation` block in `run_v3_prepublish()`:

```python
    prepublish_status = resolve_prepublish_status(
        preflight=preflight,
        asset_gate=asset_gate,
        signal_pipeline=signal_pipeline,
    )
    ready_for_confirmation = prepublish_status == "ready_for_confirmation"
    for platform in ("toutiao", "zhihu", "wechat"):
        state["platforms"].setdefault(platform, empty_platform_state())
        state["platforms"][platform]["manualConfirmRequired"] = True
        state["platforms"][platform]["formalPublishEnabled"] = False
        state["platforms"][platform]["prepublishStatus"] = prepublish_status
        state["platforms"][platform]["error"] = (
            "benchmark_inputs_stale" if prepublish_status == "blocked_by_stale_benchmark_inputs" else state["platforms"][platform].get("error")
        )
```

Do not rewrite Xiaohongshu here.

- [ ] **Step 3: Tighten the checklist required action**

Inside `build_operator_checklist()`, replace the current stale branch with a mandatory block action:

```python
    if signal_freshness == "stale":
        required_actions.insert(
            0,
            "对标输入已过期：先刷新 `benchmark-request.json` 或 `benchmark-records.jsonl`，否则今日头条、知乎、公众号不可继续预发确认。",
        )
```

- [ ] **Step 4: Extend the test with stronger assertions**

Add these assertions to the stale regression:

```python
        self.assertEqual(state["platforms"]["toutiao"]["error"], "benchmark_inputs_stale")
        self.assertEqual(state["platforms"]["zhihu"]["error"], "benchmark_inputs_stale")
        self.assertEqual(state["platforms"]["wechat"]["error"], "benchmark_inputs_stale")
        self.assertIn("不可继续预发确认", checklist)
```

- [ ] **Step 5: Run the stale regression again**

Run:

```powershell
python -m unittest tests.scripts.test_run_v3_content_ops.RunV3ContentOpsTests.test_run_v3_prepublish_blocks_when_benchmark_inputs_are_stale -v
```

Expected: PASS.

- [ ] **Step 6: Commit the state/checklist checkpoint**

Run:

```powershell
git add scripts/run_v3_content_ops.py tests/scripts/test_run_v3_content_ops.py
git commit -m "feat: hard gate stale benchmark inputs in v3 state"
```

Expected: commit records the state and checklist alignment.

## Task 4: Protect the non-stale path

**Files:**
- Modify: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_v3_content_ops.py`
- Test: `C:\Users\Administrator\Documents\code-news\scripts\run_v3_content_ops.py`

- [ ] **Step 1: Add or extend a fresh-path assertion**

Extend `test_run_v3_prepublish_runs_signal_pipeline_when_benchmark_records_exist()` with:

```python
        preview = json.loads((self.generated_dir / "publish-preview.json").read_text(encoding="utf-8"))
        self.assertEqual(state["v3"]["signalPipeline"]["freshnessStatus"], "fresh")
        self.assertEqual(preview["platforms"]["toutiao"]["status"], "manual_confirmation_required")
        self.assertEqual(state["platforms"]["toutiao"]["prepublishStatus"], "ready_for_confirmation")
```

- [ ] **Step 2: Run the focused test file**

Run:

```powershell
python -m unittest tests.scripts.test_run_v3_content_ops -v
```

Expected: PASS for both stale and fresh paths.

- [ ] **Step 3: Commit the non-regression coverage**

Run:

```powershell
git add tests/scripts/test_run_v3_content_ops.py
git commit -m "test: protect fresh path for stale benchmark gate"
```

Expected: commit contains only the added non-regression assertion.

## Task 5: Verify the whole slice end to end

**Files:**
- Verify: `C:\Users\Administrator\Documents\code-news\scripts\run_v3_content_ops.py`
- Verify: `C:\Users\Administrator\Documents\code-news\tests\scripts\test_run_v3_content_ops.py`
- Verify output: `C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-06-15-ai-night-shift-workflow-value\`

- [ ] **Step 1: Run the related test slice**

Run:

```powershell
python -m unittest tests.scripts.test_run_v3_content_ops tests.scripts.test_run_content_signal_pipeline -v
```

Expected: PASS. No regressions in signal freshness behavior.

- [ ] **Step 2: Run the real payload**

Run:

```powershell
python scripts/run_v3_content_ops.py .tmp\toutiao_payload_2026_06_15_ai_night_shift_workflow_value.json --min-score 80
```

Expected: command completes and rewrites `pipeline-state.json`, `publish-preview.json`, and `operator-checklist.md` under `.tmp/generated/2026-06-15-ai-night-shift-workflow-value/`.

- [ ] **Step 3: Inspect the generated outputs**

Run:

```powershell
Get-Content .tmp\generated\2026-06-15-ai-night-shift-workflow-value\publish-preview.json
Get-Content .tmp\generated\2026-06-15-ai-night-shift-workflow-value\pipeline-state.json
Get-Content .tmp\generated\2026-06-15-ai-night-shift-workflow-value\operator-checklist.md
```

Expected:

- If freshness remains `fresh`, the three platforms stay on the current confirmable path.
- If freshness becomes `stale`, the three platforms show `blocked_by_stale_benchmark_inputs` consistently.

- [ ] **Step 4: Commit the finished slice**

Run:

```powershell
git add scripts/run_v3_content_ops.py tests/scripts/test_run_v3_content_ops.py
git commit -m "feat: hard gate stale benchmark inputs"
```

Expected: final implementation commit after verification.

## Self-Review

- Spec coverage:
  - stale trigger condition is covered in Task 1 and Task 3
  - publish preview block is covered in Task 2
  - pipeline state alignment is covered in Task 3
  - checklist mandatory wording is covered in Task 3
  - fresh-path non-regression is covered in Task 4
- Placeholder scan:
  - no `TODO`, `TBD`, or “similar to previous task” placeholders remain
- Type consistency:
  - planned status string is consistently `blocked_by_stale_benchmark_inputs`
  - reason string is consistently `benchmark_inputs_stale`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-stale-benchmark-hard-gate.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
