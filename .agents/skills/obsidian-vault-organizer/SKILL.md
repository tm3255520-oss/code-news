---
name: obsidian-vault-organizer
description: Use when the starting point is an existing Obsidian vault or Markdown note collection and the task is cleanup, broken-link repair, duplicate merge, navigation, validation, or note-quality improvement; Chinese triggers include vault整理, 断链修复, 合并重复笔记. Use $algorithm-job-notes-for-obsidian when algorithm-job direction taxonomy, JD routes, or interview evidence is in scope; use $ppt-to-md-for-obsidian for local courseware extraction, $web-course-notes-for-obsidian for URL collection, and $notes-to-scientific-ppt when the main goal is a PPTX deck.
---

# Obsidian Vault Organizer

## Goal

Organize an existing Obsidian vault or Markdown note collection into a coherent note system without damaging source materials. Preserve local conventions, improve navigation, repair links, merge duplicate notes, and turn rough notes into usable study or research material.

Use this skill for vault-first work. If the main task is extracting or converting PPT/PPTX/PDF courseware, use `$ppt-to-md-for-obsidian` instead.

When a target vault follows solvenotes-style conventions, read `references/solvenotes-profile.md` before strict cleanup or project-specific validation. In Solvenotes, follow its manifest-only source-evidence contract, keep temporary audit ledgers outside the vault, and never create or update legacy audit notes.

## Handoff Boundaries

Use this skill when the task is vault-first: cleanup, repair, merge, navigation, validation, or note-quality improvement. If algorithm-job direction taxonomy, JD categories, or interview routes are being changed, hand off to `$algorithm-job-notes-for-obsidian` first. If source extraction from PPT/PPTX/PDF is still the main task, switch to `$ppt-to-md-for-obsidian`; if public web source collection is still required, use `$web-course-notes-for-obsidian` first.

## Dry-run Mode

When the user asks for a dry run, audit and report planned edits only. Include broken links, duplicate note stems, proposed merges, proposed renames, source files that should stay read-only, and validation commands to run. Do not modify files until the user approves the plan.

Keep backup copies, backup directories, audit notes, coverage notes, and report Markdown files outside the vault by default. Create an in-vault artifact only when the user explicitly requests one or local guidance requires it. Use the chat response, git diffs, and validation output for ordinary audits. When deleting a previously generated report, remove stale links to it.

The Solvenotes profile is stricter: its legacy audit/report pages stay forbidden even if the generic `--allow-formal-coverage-audits` compatibility flag is supplied. Record durable source limitations only through the profile's named manifest contract.

For dry-run audits and broad cleanup, run `scripts/link_inventory.py` before editing when the vault is local. Keep the baseline outside the vault unless the user explicitly asks for a file artifact inside it. After cleanup, rerun the inventory and compare total link count, per-directory link counts, and the files with the largest link-count drops before claiming link coverage was preserved.

## Quick Start

1. Resolve the vault root, source-material boundaries, local guidance, and requested edit scope.
2. Audit links, duplicate note stems, empty files, conflict markers, and local navigation before editing.
3. Build an edit plan that separates source safety, note cleanup, link repair, and generated review-page updates.
4. Apply the smallest coherent set of vault edits, preserving local naming and useful cross-links.
5. Run link and quality validation before claiming the vault is organized.

## Evidence And Assumption Gate

Treat existing notes, local guidance, source files opened in the current task, git history, and validator output as evidence. Mark source-consistency claims as assumptions unless the corresponding source material was opened or extracted. If source files are absent, limit the result to vault quality, navigation, and link integrity rather than claiming source fidelity.

## Workflow

1. Resolve the project, vault, and source boundaries.
   - Identify the vault from explicit paths, `.obsidian`, notes-like directories, or dense Markdown collections.
   - Identify source materials separately from notes.
   - Treat source files as read-only unless the user explicitly asks to rename, move, delete, or reorganize them.
   - For source-consistency claims, build a source-to-note map first. Do not claim a note is source-consistent unless its corresponding source file has been opened or extracted in the current task.
   - When course-note source checking requires PPT/PPTX text and no dedicated converter skill/tool is available, use `scripts/extract_presentation_text.py` to create temporary source text for comparison. Its output begins with extraction metadata and is only partial text evidence: it performs no OCR or complete visual/layout inspection, and speaker-note coverage is absent or unreliable. Keep the metadata separate from source text, and use the extracted hints for manual note repair, not as an automatic note generator or a complete-coverage claim.

2. Load local guidance before editing.
   - Read `AGENT.md`, `agent.md`, and relevant files under `agent/` when present.
   - Read nearby overview pages, indexes, and existing note examples.
   - Let project-local guidance override this generic skill.
   - See `references/project-vault-workflow.md` for path resolution and editing boundaries.

3. Audit the current vault shape.
   - Find navigation pages, orphan notes, broken links, self-links, duplicate topics, empty files, conflict markers, and leftover template phrases.
   - For broad cleanup, capture a pre-edit link inventory with `scripts/link_inventory.py --format json` or `--format markdown` so link coverage can be compared after edits.
   - Identify naming and numbering conventions before creating files.
   - Prefer updating an existing note over creating a duplicate.

4. Organize content.
   - Create or update overview/index notes only where they are useful.
   - Merge duplicate same-topic notes when the target is clear.
   - Keep course order, paper sequence, and concept hierarchy consistent with neighboring notes.
   - Put links where concepts first become relevant rather than dumping large link lists at the end.
   - When adding templates, learning paths, Bases instructions, or quality entry pages, treat them as navigation or workflow aids rather than course content.

5. Improve note quality.
   - Rewrite rough notes into explanations, not source dumps.
   - Preserve Chinese as the default language when the vault uses Chinese.
   - Keep standard English technical terms where appropriate.
   - Add formula variable meanings, assumptions, examples, failure cases, and boundaries when useful.
   - Preserve frontmatter fields that local scripts or Obsidian Properties rely on.
   - For course notes, process one source or one chapter at a time when the user requests strict checking; avoid broad mechanical rewrites that hide source-consistency errors.
   - When checking all courses, finish and validate one course directory before moving to the next. If a course lacks source materials, say that directly and limit the claim to note quality and link integrity.
   - Treat project-local standalone systems, such as concept indexes, research-method notes, or job-prep/topic notes, as independent note systems when local guidance says they do not mirror a source directory. Do not invent a source map for them; validate internal consistency, link integrity, and concrete explanations instead.
   - Keep generated review pages clearly labeled as review pages when they do not correspond to a single source file.
   - For paper notes, normalize substantial existing content into `## 可复现要点` and `## 失败边界` when the local review checklist expects those headings. Do not add empty headings. If code or checkpoint availability is not recorded in the note, state that limitation rather than guessing.
   - Remove generic filler, repeated section templates, stale cross-course links, and report-style audit prose from study notes.
   - Before and after broad cleanup, compare link coverage against a saved inventory when available. Treat unexplained large link loss as a regression even when broken links are zero.
   - When removing stale navigation/report links, preserve concept links that still support prerequisites, follow-up topics, formulas, examples, sources, or comparisons.
   - After rewriting chapter notes, update overview, review pages, and local navigation that repeat changed titles or scope.
   - If a note or directory is renamed for clarity, preserve old wiki-link entry points with short bridge notes when the old path may still be referenced. Bridge notes must be explicit redirects to the new note, not duplicate content.
   - Treat unrelated-domain formula explanations as source-mismatch residues. Replace them only after checking the corresponding source.
   - See `references/obsidian-style.md` for style guidance.

6. Validate before finishing.
   - Run `scripts/check_obsidian_links.py` for Markdown and Obsidian wiki links when the vault is local.
   - The bundled link checker masks fenced and inline code before scanning. Code-like double brackets outside code spans, such as R `x[[1]]` in prose, still need escaping/rephrasing; never claim link validation is clean until the checker and a code-block regression test pass.
   - Run `scripts/check_vault_quality.py` for conflict markers, empty files, unbalanced block math, duplicate note stems, and leftover template text.
   - For strict cleanup, also run `scripts/check_vault_quality.py --strict-study --forbid-report-notes` on the affected note directory. Use `--profile solvenotes` only after reading `references/solvenotes-profile.md`, and use `--pattern-file` for project-specific residue lists.
   - Under `--profile solvenotes`, `99_内容覆盖审查.md` and `coverage_audit` report pages fail closed. The generic profile may use `--allow-formal-coverage-audits` for a different vault's typed legacy contract.
   - If a checked course contains an independently validated nested topic, pass its exact root-relative path with repeatable `--skip-dir` and validate that topic separately. Read `references/solvenotes-profile.md` for the exact-path and fail-closed rules.
   - Run the targeted residue scan over chapter notes, overviews, and generated review pages together. Review pages often preserve old formula snippets and cross-course links after chapters have been fixed.
   - Classify residue-scan hits before editing. Words such as "report", "audit", "review", or "template" can be legitimate course terms in software engineering, databases, security, CS231n, or project courses; remove them only when they are stale note scaffolding, not when they are part of the taught concept.
   - See `references/validation.md` for lightweight checks.
   - In repositories with local validators, prefer the local suite over bundled generic scripts.
   - Before upload, run `git status` in each affected repository, stage only intended files, and leave unrelated dirty files untouched. If both a notes repository and a skill repository changed, validate, commit, and push them separately.

## Common Tasks

- Merge newly written notes into an existing vault.
- Repair broken `[[wiki]]` and Markdown links.
- Build or update `00_课程总览.md`, `00_学习地图.md`, concept indexes, and review pages.
- Clean duplicated topic notes while preserving the better content.
- Reconcile note names, numbering, and cross-links after a course or project update.
- Audit a vault and report safe edits separately from source-file findings.

## Quality Bar

Good vault organization should make the note system easier to navigate without hiding source provenance or local conventions. The final vault should have clear entry points, stable filenames, useful cross-links, no accidental source-file edits, and no new duplicate same-topic notes.

Avoid generic study templates, empty boilerplate sections, report files masquerading as notes, broad rewrites unrelated to the request, and moving source materials into the vault without explicit permission.

## Output Contract

The final response should include:

- vault path and scope that were actually inspected,
- files created, updated, merged, renamed, or intentionally left untouched,
- source-file safety status, especially if source materials were found near notes,
- validation performed, including link and quality checks when run,
- unresolved broken links, duplicate candidates, naming conflicts, or local-guidance assumptions.

For dry-run work, clearly separate proposed edits from applied edits and do not claim changes were made.

## Bundled Resources

- `scripts/check_obsidian_links.py`: check Markdown links and Obsidian wiki links while ignoring fenced and inline code.
- `scripts/check_vault_quality.py`: check empty files, conflict markers, unbalanced fences/math, duplicate note stems, template residue, generic strict-study link placement, optional solvenotes profile residue, fail-closed Solvenotes legacy audit pages, and custom pattern files.
- `scripts/link_inventory.py`: inventory Markdown, wiki, and external links by file and directory for cleanup before/after comparisons.
- `scripts/extract_presentation_text.py`: extract partial PPTX and legacy PPT text hints into temporary files with explicit non-OCR, visual, and speaker-note coverage limits.
- `references/project-vault-workflow.md`: path discovery, local guidance loading, and editing boundaries.
- `references/obsidian-style.md`: note writing, formulas, links, navigation, and review page style.
- `references/validation.md`: lightweight validation checks for vault edits.
- `references/solvenotes-profile.md`: optional solvenotes-style cleanup, link-coverage, and validation profile.
