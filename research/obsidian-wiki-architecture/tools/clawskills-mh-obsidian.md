Source: https://clawskills.sh/skills/mohdalhashemi98-hue-mh-obsidian
Fetched: 2026-08-01T10:39:08

Title: mh-obsidian — OpenClaw Skill | clawskills.sh

URL Source: http://clawskills.sh/skills/mohdalhashemi98-hue-mh-obsidian

Markdown Content:
[LaunchKit · 2026— Production-ready starter kit for websites, SaaS, and AI tools→](https://launchkit.getdesign.md/)

[claw skills.sh](http://clawskills.sh/)[OpenClaw Use Cases](http://clawskills.sh/openclaw/usecases)[Integrations](http://clawskills.sh/openclaw/integrations/github)[About](http://clawskills.sh/about)

[Star 51.6k](https://github.com/VoltAgent/awesome-openclaw-skills)

[Sign in](http://clawskills.sh/auth)

[Back to Skills](http://clawskills.sh/skills)

# mh-obsidian

[DevOps & Cloud](http://clawskills.sh/skills?category=DevOps+%26+Cloud)v 1.0.0

Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli.

0

979 downloads

by @mohdalhashemi98-hue

[Save skill](http://clawskills.sh/auth?next=%2Fskills%2Fmohdalhashemi98-hue-mh-obsidian)

### Security Audits

VirusTotal Benign

[Report →](https://www.virustotal.com/gui/file/b98da3ddc339e8f87ac744a257444ec37a96819b87334b95eef7eadf66a903ac)

OpenClaw Benign

These signals reflect official OpenClaw status values. A Suspicious status means the skill should be used with extra caution.

[Sponsorship Feature your brand here→ Reach developers exploring OpenClaw](https://sponsors.voltagent.dev/#clawskills.sh)

## Setup & Installation

CLI Prompt

openclaw skills install @mohdalhashemi98-hue/mh-obsidian

Or with the ClawHub CLI, for registry-managed skill folders outside a full OpenClaw workspace:

npx clawhub install mh-obsidian

[View on ClawHub](https://clawhub.ai/mohdalhashemi98-hue/mh-obsidian)[Download SKILL.md](http://clawskills.sh/skills-markdown/mohdalhashemi98-hue/mh-obsidian.md)

## What This Skill Does

Interact with Obsidian vaults from the command line using obsidian-cli. Supports searching, creating, moving, and deleting notes while preserving wikilink integrity across the vault.

Moving or renaming notes via obsidian-cli updates all wikilinks vault-wide, which a plain file rename does not.

### When to use it

*   Search note content for a forgotten idea across a large vault
*   Create a new note from a script or template automatically
*   Rename a note without breaking wikilinks to it
*   Find which vault is currently active on a machine
*   Batch-create meeting notes from a scheduled workflow

View original SKILL.md file

---
name: obsidian
description: Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli.
homepage: https://help.obsidian.md
metadata:
  {
    "openclaw":
      {
        "emoji": "💎",
        "requires": { "bins": ["obsidian-cli"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "yakitrak/yakitrak/obsidian-cli",
              "bins": ["obsidian-cli"],
              "label": "Install obsidian-cli (brew)",
            },
          ],
      },
  }
---

# Obsidian

Obsidian vault = a normal folder on disk.

Vault structure (typical)

- Notes: `*.md` (plain text Markdown; edit with any editor)
- Config: `.obsidian/` (workspace + plugin settings; usually don’t touch from scripts)
- Canvases: `*.canvas` (JSON)
- Attachments: whatever folder you chose in Obsidian settings (images/PDFs/etc.)

## Find the active vault(s)

Obsidian desktop tracks vaults here (source of truth):

- `~/Library/Application Support/obsidian/obsidian.json`

`obsidian-cli` resolves vaults from that file; vault name is typically the **folder name** (path suffix).

Fast “what vault is active / where are the notes?”

- If you’ve already set a default: `obsidian-cli print-default --path-only`
- Otherwise, read `~/Library/Application Support/obsidian/obsidian.json` and use the vault entry with `"open": true`.

Notes

- Multiple vaults common (iCloud vs `~/Documents`, work/personal, etc.). Don’t guess; read config.
- Avoid writing hardcoded vault paths into scripts; prefer reading the config or using `print-default`.

## obsidian-cli quick start

Pick a default vault (once):

- `obsidian-cli set-default "<vault-folder-name>"`
- `obsidian-cli print-default` / `obsidian-cli print-default --path-only`

Search

- `obsidian-cli search "query"` (note names)
- `obsidian-cli search-content "query"` (inside notes; shows snippets + lines)

Create

- `obsidian-cli create "Folder/New note" --content "..." --open`
- Requires Obsidian URI handler (`obsidian://…`) working (Obsidian installed).
- Avoid creating notes under “hidden” dot-folders (e.g. `.something/...`) via URI; Obsidian may refuse.

Move/rename (safe refactor)

- `obsidian-cli move "old/path/note" "new/path/note"`
- Updates `[[wikilinks]]` and common Markdown links across the vault (this is the main win vs `mv`).

Delete

- `obsidian-cli delete "path/note"`

Prefer direct edits when appropriate: open the `.md` file and change it; Obsidian will pick it up.

## Example Workflow

Here's how your AI assistant might use this skill in practice.

INPUT

User asks: find all notes mentioning 'project alpha' and create a summary note

AGENT

1.   1 Run obsidian-cli print-default --path-only to confirm the active vault path
2.   2 Run obsidian-cli search-content 'project alpha' to retrieve matching notes and snippets
3.   3 Compile relevant excerpts into a summary string
4.   4 Run obsidian-cli create 'Projects/Project Alpha Summary' --content '<summary>' --open

OUTPUT

A new note at Projects/Project Alpha Summary is created in the vault and opened in Obsidian

## Requirements

Accounts, API keys, or tools you or your AI assistant may need to set up while using this skill.

obsidian-cli installed (brew install yakitrak/yakitrak/obsidian-cli)Obsidian desktop app installed with URI handler active

[Save skill](http://clawskills.sh/auth?next=%2Fskills%2Fmohdalhashemi98-hue-mh-obsidian)

### Security Audits

VirusTotal Benign

[Report →](https://www.virustotal.com/gui/file/b98da3ddc339e8f87ac744a257444ec37a96819b87334b95eef7eadf66a903ac)

OpenClaw Benign

These signals reflect official OpenClaw status values. A Suspicious status means the skill should be used with extra caution.

[Sponsorship Feature your brand here→ Reach developers exploring OpenClaw](https://sponsors.voltagent.dev/#clawskills.sh)

## Similar Skills

[VIEW ALL](http://clawskills.sh/skills?category=DevOps+%26+Cloud)

### [api-gateway API gateway for calling third-party APIs with managed auth. 45.7k 225](http://clawskills.sh/skills/byungkyu-api-gateway)### [ai-act-risk-check **Description:** Quickly assesses a preliminary risk classification for an AI system based on the high-risk. 10.8k 0](http://clawskills.sh/skills/bluesbell-ai-act-risk-check)### [agent-directory The directory for AI agent services. 5.4k 13](http://clawskills.sh/skills/aerialcombat-agent-directory)### [aws-infra Chat-based AWS infrastructure assistance using AWS CLI and console. 4.0k 3](http://clawskills.sh/skills/bmdhodl-aws-infra)

claw skills.sh— Independent index of public ClawHub/OpenClaw skills. Not affiliated with OpenClaw.

Feedback

