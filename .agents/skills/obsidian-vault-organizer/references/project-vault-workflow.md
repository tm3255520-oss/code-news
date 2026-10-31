# Project Vault Workflow

Use this reference when organizing, repairing, or merging notes inside an existing Obsidian vault or Markdown note collection.

## Path Resolution

Do not hard-code absolute paths from examples or previous runs. Resolve paths in this order:

1. Use explicit paths in the user prompt.
2. Treat the current working directory as the first project-root candidate when the user says "this repo", "here", or similar.
3. Detect the Obsidian vault from explicit prompt text first, then from `.obsidian`, a `notes`-like directory, or many Markdown files with course/topic subdirectories.
4. Detect source materials from explicit prompt text first, then from non-vault directories containing requested PDFs, PPT/PPTX, DOCX, papers, datasets, or Markdown sources.
5. If several candidates remain plausible, inspect directory names and local guidance before asking.

Keep these roles clear:

- `<repo_root>`: project containing source materials, vault, and guidance.
- `<vault_path>`: Obsidian vault to modify.
- `<source_path>`: source material directory or file set to read.
- `<guidance_paths>`: `AGENT.md`, `agent.md`, and files under `agent/`.

## Load Local Guidance

Before changing notes, read relevant local guidance when present:

- `AGENT.md` or `agent.md`.
- Markdown files under `agent/`.
- Existing overview pages, indexes, and nearby notes.

Project guidance takes precedence over this generic skill. Extract:

- source-to-vault directory mappings,
- writable and read-only areas,
- naming and numbering conventions,
- overview/index/review page expectations,
- formula, link, language, and final-report expectations,
- special-case directories that should not be treated like ordinary courses.

## Editing Boundaries

Default to modifying only the resolved vault and user-authorized guidance files. Treat original source materials as read-only unless the user explicitly asks to rename, move, delete, deduplicate, or reorganize them.

Do not initialize a project-root Git repository, move source directories into the vault, or change source-material folders unless directly requested.

## Routing And Naming

Prefer updating or rewriting an existing matching note over creating a duplicate. Create a new note only when no suitable note exists.

When creating a note:

- preserve the vault's filename language, separators, and numbering scheme,
- use a topic title that reflects the actual content,
- keep course or paper sequence consistent with neighboring notes,
- avoid boilerplate sections absent from the vault's local style.

Update navigation files only when they already function as navigation or project guidance requires them.

## Writing Standards

Write primary notes, not source dumps:

- Course notes explain concepts, mechanisms, formulas, examples, failure modes, and boundaries.
- Paper notes explain problem gap, assumptions, method, data flow, objective, evaluation, limitations, and boundary conditions.
- Concept index notes act as cross-topic hubs, not ordinary chapter summaries.
- Review notes should preserve the project's required detailed/concise split when present.

Avoid generic learning advice, fixed study templates, empty bridge sentences, repeated filler phrasing, and slide translation without explanation.

## Final Checks

Before finishing substantial edits, check:

- broken Obsidian links,
- self-links,
- unbalanced `$$` block math delimiters,
- control characters or extraction garbage,
- duplicate same-topic notes introduced by the change,
- navigation pages that were not updated after adding new chapter notes.

Report source-file audit findings separately when they were intentionally left untouched.
