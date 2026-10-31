Source: https://clawskills.sh/skills/skridlevsky-graphthulhu
Fetched: 2026-08-01T10:39:04

Title: graphthulhu — OpenClaw Skill | clawskills.sh

URL Source: http://clawskills.sh/skills/skridlevsky-graphthulhu

Markdown Content:
[LaunchKit · 2026— Production-ready starter kit for websites, SaaS, and AI tools→](https://launchkit.getdesign.md/)

[claw skills.sh](http://clawskills.sh/)[OpenClaw Use Cases](http://clawskills.sh/openclaw/usecases)[Integrations](http://clawskills.sh/openclaw/integrations/github)[About](http://clawskills.sh/about)

[Star...](https://github.com/VoltAgent/awesome-openclaw-skills)

[Sign in](http://clawskills.sh/auth)

[Back to Skills](http://clawskills.sh/skills)

# graphthulhu

[DevOps & Cloud](http://clawskills.sh/skills?category=DevOps+%26+Cloud)v 1.0.0

Knowledge graph MCP server for Logseq and Obsidian. 37 tools for reading, writing, searching, and analyzing.

0

272 downloads

by @skridlevsky

[Save skill](http://clawskills.sh/auth?next=%2Fskills%2Fskridlevsky-graphthulhu)

### Security Audits

VirusTotal Benign

[Report →](https://www.virustotal.com/gui/file/13a7629b9e7b5ad909deadfb54a3c3430484a1998fcf6fdfdb099cec29d36c96)

OpenClaw Suspicious

These signals reflect official OpenClaw status values. A Suspicious status means the skill should be used with extra caution.

[Sponsorship Feature your brand here→ Reach developers exploring OpenClaw](https://sponsors.voltagent.dev/#clawskills.sh)

## Setup & Installation

CLI Prompt

openclaw skills install @skridlevsky/graphthulhu

Or with the ClawHub CLI, for registry-managed skill folders outside a full OpenClaw workspace:

npx clawhub install graphthulhu

[View on ClawHub](https://clawhub.ai/skridlevsky/graphthulhu)[Download SKILL.md](http://clawskills.sh/skills-markdown/skridlevsky/graphthulhu.md)

## What This Skill Does

MCP server that provides read and write access to Logseq and Obsidian knowledge graphs. Covers 37 tools across navigation, search, writing, analysis, decisions, journals, flashcards, and whiteboards.

Obsidian support requires no plugins and reads .md files directly, while Logseq support uses the built-in HTTP API for full bidirectional access.

### When to use it

*   Search notes for a topic and find all connected pages
*   Append blocks to existing Obsidian pages from a chat interface
*   Log a decision with a deadline and check its status later
*   Review SRS flashcard due dates without opening Logseq
*   Detect orphaned notes and knowledge gaps across a vault

View original SKILL.md file

---
name: graphthulhu
description: Knowledge graph MCP server for Logseq and Obsidian. 37 tools for reading, writing, searching, and analyzing your second brain.
metadata:
  openclaw:
    requires:
      bins:
        - graphthulhu
---

# graphthulhu

MCP server that gives you full access to a Logseq or Obsidian knowledge graph. 37 tools across 9 categories: navigate, search, analyze, write, decisions, journals, flashcards, whiteboards, and health.

## Install

Download the binary for your platform from [GitHub Releases](https://github.com/skridlevsky/graphthulhu/releases) and put it on your PATH.

Or: `go install github.com/skridlevsky/graphthulhu@latest`

## Configure

### Obsidian

Add to your MCP settings:

```json
{
  "mcpServers": {
    "graphthulhu": {
      "command": "graphthulhu",
      "args": ["--backend", "obsidian", "--vault", "/path/to/your/vault"]
    }
  }
}
```

No plugins required. Reads `.md` files directly. Full read-write support.

### Logseq

Enable the HTTP API server in Logseq (Settings > Features > HTTP APIs server), start it, and create a token.

```json
{
  "mcpServers": {
    "graphthulhu": {
      "command": "graphthulhu",
      "env": {
        "LOGSEQ_API_URL": "http://127.0.0.1:12315",
        "LOGSEQ_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

## What you can do

- **Navigate** — get pages with full block trees, traverse the link graph, list pages by namespace/tag/property
- **Search** — full-text search with context, property queries, tag hierarchy search, raw Datalog (Logseq)
- **Analyze** — graph overview, find connections between pages, detect knowledge gaps and orphans, discover topic clusters
- **Write** — create pages, append/upsert blocks with nested children, update/delete/move blocks, link pages bidirectionally, rename pages with link updates, bulk update properties
- **Decisions** — create decisions with deadlines, check status, resolve or defer with tracking
- **Journals** — read entries by date range, search within journals
- **Flashcards** — SRS stats, due cards, create new cards (Logseq)
- **Whiteboards** — list and inspect spatial canvases (Logseq)

## Links

- [GitHub](https://github.com/skridlevsky/graphthulhu)
- [Full tool reference](https://github.com/skridlevsky/graphthulhu#tools)

## Example Workflow

Here's how your AI assistant might use this skill in practice.

INPUT

User asks: Find all my notes on distributed systems and show me how they connect

AGENT

1.   1 Runs full-text search across the vault for the topic
2.   2 Fetches page content and block trees for matching results
3.   3 Traverses the link graph to find connections between related pages
4.   4 Returns a summary of linked pages and flags any orphaned or unlinked notes

OUTPUT

A list of relevant pages with their connections and a note on topics not linked to the cluster

## Requirements

Accounts, API keys, or tools you or your AI assistant may need to set up while using this skill.

graphthulhu binary installed on PATH (download from GitHub Releases or via go install)LOGSEQ_API_TOKEN environment variable (Logseq users only, generated in Logseq Settings > Features > HTTP APIs server)

[Save skill](http://clawskills.sh/auth?next=%2Fskills%2Fskridlevsky-graphthulhu)

### Security Audits

VirusTotal Benign

[Report →](https://www.virustotal.com/gui/file/13a7629b9e7b5ad909deadfb54a3c3430484a1998fcf6fdfdb099cec29d36c96)

OpenClaw Suspicious

These signals reflect official OpenClaw status values. A Suspicious status means the skill should be used with extra caution.

[Sponsorship Feature your brand here→ Reach developers exploring OpenClaw](https://sponsors.voltagent.dev/#clawskills.sh)

## Similar Skills

[VIEW ALL](http://clawskills.sh/skills?category=DevOps+%26+Cloud)

### [api-gateway API gateway for calling third-party APIs with managed auth. 45.7k 225](http://clawskills.sh/skills/byungkyu-api-gateway)### [ai-act-risk-check **Description:** Quickly assesses a preliminary risk classification for an AI system based on the high-risk. 10.8k 0](http://clawskills.sh/skills/bluesbell-ai-act-risk-check)### [agent-directory The directory for AI agent services. 5.4k 13](http://clawskills.sh/skills/aerialcombat-agent-directory)### [aws-infra Chat-based AWS infrastructure assistance using AWS CLI and console. 4.0k 3](http://clawskills.sh/skills/bmdhodl-aws-infra)

claw skills.sh— Independent index of public ClawHub/OpenClaw skills. Not affiliated with OpenClaw.

Feedback

