# Traffic War Room Workflow

Updated: 2026-05-24

## Goal

Use peer samples and our own content metrics to improve three numbers:

- views
- likes
- comments

This workflow turns daily observations into weekly editorial decisions.

## Files

- Peer sample log: `C:\Users\Administrator\Documents\code-news\docs\templates\peer-content-samples.csv`
- Peer insight report script: `C:\Users\Administrator\Documents\code-news\scripts\generate_peer_content_insights.py`
- Our content log: `C:\Users\Administrator\Documents\code-news\docs\templates\content-performance-log.csv`
- Our content report script: `C:\Users\Administrator\Documents\code-news\scripts\generate_content_performance_report.py`

## Daily Loop

### Morning

Log 3 to 5 strong peer posts into the peer sample file.

For each post, capture:

- platform
- account name
- title
- topic
- angle
- hook type
- cover type
- CTA type
- views
- likes
- comments

### Evening

Recheck the same posts and update the latest views, likes, and comments.

Do not chase every post. Only keep samples that can teach us something reusable.

## Weekly Loop

### 1. Generate the peer report

```powershell
python C:\Users\Administrator\Documents\code-news\scripts\generate_peer_content_insights.py `
  C:\Users\Administrator\Documents\code-news\docs\templates\peer-content-samples.csv `
  --output C:\Users\Administrator\Documents\code-news\.tmp\peer-content-insights.md
```

### 2. Generate our own performance report

```powershell
python C:\Users\Administrator\Documents\code-news\scripts\generate_content_performance_report.py `
  C:\Users\Administrator\Documents\code-news\docs\templates\content-performance-log.csv `
  --output C:\Users\Administrator\Documents\code-news\.tmp\content-performance-report.md
```

### 3. Make next-post decisions

Before writing the next article, pull out:

- 1 topic pattern to reuse
- 1 title pattern to test
- 1 opening hook to test
- 1 comment prompt to test

Do not change everything at once. Change 2 or 3 variables, then check what moved.

## Field Definitions

- `topic`: What the post is about. Example: `ai-tools`, `agent-workflow`, `product-analysis`
- `angle`: What promise the post makes. Example: `case-study`, `warning`, `tutorial`, `trend-explainer`
- `format`: Delivery format. Example: `long-article`, `qa`, `carousel`, `roundup`
- `hook_type`: The first mental trigger. Example: `result-first`, `conflict-first`, `question-first`, `mistake-first`
- `cover_type`: The cover style. Example: `data-card`, `comparison-card`, `single-visual`, `three-image`
- `cta_type`: The discussion prompt style. Example: `ask-choice`, `ask-experience`, `ask-prediction`, `none`

## Rules

1. Track patterns, not just titles.
2. Prefer reusable posts over one-off viral accidents.
3. A post with strong comments can be more valuable than a post with only raw views.
4. If a pattern wins across multiple accounts, promote it faster into our next draft.
5. If a pattern wins on one platform but not another, keep the platform difference instead of forcing one style everywhere.

## What Good Looks Like

Each week we should be able to answer:

- Which topics are pulling views?
- Which title and hook patterns are lifting likes?
- Which CTA styles are lifting comments?
- Which 3 changes will we test in the next publishing cycle?
