Source: https://clawskills.sh/skills/anshumanbh-anshumanbh-qmd
Fetched: 2026-08-01T10:39:11

Title: anshumanbh-qmd — OpenClaw Skill | clawskills.sh

URL Source: http://clawskills.sh/skills/anshumanbh-anshumanbh-qmd

Markdown Content:
[LaunchKit · 2026— Production-ready starter kit for websites, SaaS, and AI tools→](https://launchkit.getdesign.md/)

[claw skills.sh](http://clawskills.sh/)[OpenClaw Use Cases](http://clawskills.sh/openclaw/usecases)[Integrations](http://clawskills.sh/openclaw/integrations/github)[About](http://clawskills.sh/about)

[Star 51.6k](https://github.com/VoltAgent/awesome-openclaw-skills)

[Sign in](http://clawskills.sh/auth)

[Back to Skills](http://clawskills.sh/skills)

# anshumanbh-qmd

[Search & Research](http://clawskills.sh/skills?category=Search+%26+Research)v 1.0.0

Search markdown knowledge bases efficiently.

0

1.9k downloads

by @anshumanbh

[Save skill](http://clawskills.sh/auth?next=%2Fskills%2Fanshumanbh-anshumanbh-qmd)

### Security Audits

VirusTotal Suspicious

[Report →](https://www.virustotal.com/gui/file/c613d2e64dcef8290474a553f036a297763545aafede17c706d798b8733f9061)

OpenClaw Benign

These signals reflect official OpenClaw status values. A Suspicious status means the skill should be used with extra caution.

[Sponsorship Feature your brand here→ Reach developers exploring OpenClaw](https://sponsors.voltagent.dev/#clawskills.sh)

## Setup & Installation

CLI Prompt

openclaw skills install @anshumanbh/anshumanbh-qmd

Or with the ClawHub CLI, for registry-managed skill folders outside a full OpenClaw workspace:

npx clawhub install anshumanbh-qmd

[View on ClawHub](https://clawhub.ai/anshumanbh/anshumanbh-qmd)[Download SKILL.md](http://clawskills.sh/skills-markdown/anshumanbh/anshumanbh-qmd.md)

## What This Skill Does

qmd indexes local markdown files and returns relevant snippets using BM25 keyword matching and vector embeddings. It targets Obsidian vaults and similar markdown collections. Searches return file paths and context excerpts rather than full file contents.

Returns only relevant snippets instead of full files, cutting token usage by roughly 96% compared to reading markdown files directly into the context window.

### When to use it

*   Finding a specific note in a large Obsidian vault
*   Searching personal knowledge bases by concept
*   Locating technical documentation by keyword
*   Retrieving past meeting notes or project decisions
*   Querying a markdown journal without reading every file

View original SKILL.md file

---
name: qmd
description: Search markdown knowledge bases efficiently using qmd. Use this when searching Obsidian vaults or markdown collections to find relevant content with minimal token usage.
argument-hint: "<search query> [--collection <name>] [--semantic]"
---

# QMD Search Skill

Search markdown knowledge bases efficiently using qmd, a local indexing tool that uses BM25 + vector embeddings to return only relevant snippets instead of full files.

## Why Use This

- **96% token reduction** - Returns relevant snippets instead of reading entire files
- **Instant results** - Pre-indexed content means fast searches
- **Local & private** - All indexing and search happens locally
- **Hybrid search** - BM25 for keyword matching, vector search for semantic similarity

## Commands

### Search (BM25 keyword matching)
```bash
qmd search "your query" --collection <name>
```
Fast, accurate keyword-based search. Best for specific terms or phrases.

### Vector Search (semantic)
```bash
qmd vsearch "your query" --collection <name>
```
Semantic similarity search. Best for conceptual queries where exact words may vary.

### Hybrid Search (both + reranking)
```bash
qmd hybrid "your query" --collection <name>
```
Combines both approaches with LLM reranking. Most thorough but often overkill.

## How to Use

1. **Check if collection exists**:
   ```bash
   qmd collection list
   ```

2. **Search the collection**:
   ```bash
   # For specific terms
   qmd search "api authentication" --collection notes

   # For conceptual queries
   qmd vsearch "how to handle errors gracefully" --collection notes
   ```

3. **Read results**: qmd returns relevant snippets with file paths and context

## Setup (if qmd not installed)

```bash
# Install qmd
bun install -g https://github.com/tobi/qmd

# Add a collection (e.g., Obsidian vault)
qmd collection add ~/path/to/vault --name notes

# Generate embeddings for vector search
qmd embed --collection notes
```

## Invocation Examples

```
/qmd api authentication          # BM25 search for "api authentication"
/qmd how to handle errors --semantic   # Vector search for conceptual query
/qmd --setup                     # Guide through initial setup
```

## Best Practices

- Use **BM25 search** (`qmd search`) for specific terms, names, or technical keywords
- Use **vector search** (`qmd vsearch`) when looking for concepts where wording may vary
- Avoid hybrid search unless you need maximum recall - it's slower
- Re-run `qmd embed` after adding significant new content to keep vectors current

## Handling Arguments

- `$ARGUMENTS` contains the full search query
- If `--semantic` flag is present, use `qmd vsearch` instead of `qmd search`
- If `--setup` flag is present, guide user through installation and collection setup
- If `--collection <name>` is specified, use that collection; otherwise default to checking available collections

## Workflow

1. Parse arguments from `$ARGUMENTS`
2. Check if qmd is installed (`which qmd`)
3. If not installed, offer to guide setup
4. If searching:
   - List collections if none specified
   - Run appropriate search command
   - Present results to user with file paths
5. If user wants to read a specific result, use the Read tool on the file path

## Example Workflow

Here's how your AI assistant might use this skill in practice.

INPUT

User asks: find my notes on API authentication

AGENT

1.   1 Parse 'api authentication' as search query from arguments
2.   2 Check that qmd is installed with 'which qmd'
3.   3 List available collections with 'qmd collection list'
4.   4 Run 'qmd search "api authentication" --collection notes'
5.   5 Present returned snippets with file paths to the user

OUTPUT

Relevant snippet excerpts from matching notes, each with a file path for direct reference

## Requirements

Accounts, API keys, or tools you or your AI assistant may need to set up while using this skill.

qmd installed via Bun from github.com/tobi/qmd Bun runtime (required to install qmd globally)

[Save skill](http://clawskills.sh/auth?next=%2Fskills%2Fanshumanbh-anshumanbh-qmd)

### Security Audits

VirusTotal Suspicious

[Report →](https://www.virustotal.com/gui/file/c613d2e64dcef8290474a553f036a297763545aafede17c706d798b8733f9061)

OpenClaw Benign

These signals reflect official OpenClaw status values. A Suspicious status means the skill should be used with extra caution.

[Sponsorship Feature your brand here→ Reach developers exploring OpenClaw](https://sponsors.voltagent.dev/#clawskills.sh)

## Similar Skills

[VIEW ALL](http://clawskills.sh/skills?category=Search+%26+Research)

### [baidu-search Search the web using Baidu AI Search Engine (BDSE). 45.2k 112](http://clawskills.sh/skills/ide-rea-baidu-search)### [answeroverflow Search indexed Discord community discussions via Answer. 12.3k 123](http://clawskills.sh/skills/rhyssullivan-answeroverflow)### [academic-deep-research Transparent, rigorous research with full. 10.8k 38](http://clawskills.sh/skills/kesslerio-academic-deep-research)### [arxiv-watcher Search and summarize papers from ArXiv. 6.9k 6](http://clawskills.sh/skills/rubenfb23-arxiv-watcher)

claw skills.sh— Independent index of public ClawHub/OpenClaw skills. Not affiliated with OpenClaw.

Feedback

