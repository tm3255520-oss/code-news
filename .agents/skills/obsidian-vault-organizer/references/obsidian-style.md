# Obsidian Note Style

## Naming

- Preserve the vault's existing language, separators, and numbering scheme.
- Use numbered files for ordered course chapters when neighboring notes already do: `01_绪论.md`, `02_搜索策略.md`.
- Use entry pages such as `00_课程总览.md`, `00_学习地图.md`, `README.md`, or an existing index only when they match local style.
- Keep detailed and concise review files separate when the vault already uses that convention.

## Writing

- Write in Chinese by default when the vault uses Chinese.
- Keep standard English technical terms when they are the normal name.
- Expand rough bullets into coherent explanations when the user asks for content improvement.
- Do not keep generic source phrases if they do not help learning or recall.
- Add examples or boundary cases when a concept is easy to misuse.

## Formulas

- Use block math when the vault already supports it:

```markdown
$$
L(\theta)=\frac{1}{N}\sum_{i=1}^{N}\ell(f_\theta(x_i), y_i)
$$
```

- Explain variables near the formula.
- Explain what the formula is used for in the current topic.
- Avoid copying formulas without context.

## Links

- Prefer the vault's existing link style. Use Obsidian wiki links when no other convention is clear:

```markdown
[[机器学习/05_模型的泛化能力|泛化能力]]
```

- Put links where the related concept first appears.
- Avoid repeated trailing link dumps.
- Navigation pages and concept indexes may be link-heavy.

## Review And Index Pages

- Detailed review pages should preserve mechanisms, assumptions, formulas, and failure cases.
- Concise review pages should keep the main chain, core formulas, frequent mistakes, and links back to detailed notes.
- Concept indexes should link across topics and courses without becoming chapter summaries.

## Source Provenance

When notes are derived from source materials, preserve useful source references in the note body or nearby metadata if the vault already does so. Do not move, rename, or delete source materials unless the user explicitly asks.
