# Migrating into OKF

Goal: turn existing notes into a **conformant** bundle without inventing data. The deterministic
tool does the mechanical work; you supply judgment for `type` and cross-links.

## The fast path (deterministic)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" migrate <src-dir> --out <bundle>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" index <bundle> --recursive --write
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" validate <bundle>
```

`migrate` walks every `.md` under `<src-dir>` and for each note:
- ensures frontmatter with a non-empty `type` (default `Note`; pass `--default-type` to change);
- infers `title` (existing frontmatter → first `# H1` → filename) and `description` (first
  paragraph) and `timestamp` (file mtime) — **only when absent**;
- rewrites `[[wikilink]]` and `[[wikilink|alias]]` into bundle-relative Markdown links,
  resolving each target by filename- or title-slug against the other notes;
- preserves any existing frontmatter keys verbatim (including unknown ones).

It does **not** touch the source unless you pass `--write`; `--out DIR` writes a fresh bundle
and copies non-Markdown assets (images, `references/`) across. Dry-run (neither flag) prints a
plan: notes found, type added, wikilinks converted, and any unresolved links.

## Choosing `type`

`type` is free-form and is the one thing the tool cannot infer honestly. Defaulting to `Note`
is fine for a personal wiki. For a richer bundle, decide types by directory or topic and pass
`--default-type`, or set them per file afterward. **Never fabricate a precise type** (e.g. do
not label a freeform note `BigQuery Table`); leave the generic `Note` and refine deliberately.

## Source-specific field mappings

You apply these (the tool handles Markdown + wikilinks; the rest is judgment):

### Obsidian vault
| Obsidian | OKF |
|----------|-----|
| `[[Note]]` / `[[Note\|alias]]` | Markdown link to the concept (the tool does this) |
| `![[embed]]` | Inline the content or link it; OKF has no transclusion |
| `#tag` inline or `tags:` frontmatter | `tags:` YAML list |
| nested folders | bundle subdirectories (kept as-is) |

### Notion export (Markdown & CSV)
| Notion | OKF |
|--------|-----|
| page title (`# H1`) | `title` |
| a "Type"/"Category" property | `type` |
| "Last edited" | `timestamp` (ISO 8601) |
| URL/property links between pages | bundle-relative Markdown links |
| other properties | frontmatter keys (kept; unknown keys are allowed) |

### CSV / spreadsheet
One **row per concept**. Map a column to `type` (required), one to `title`, others to
frontmatter keys or a `# Schema` table. Put the row's prose into the body.

## After migrating
- Run `validate`; fix every **error** (e.g. a TODO `type` left blank → `E005`).
- Burn down warnings as polish: add `description`/`timestamp`, fix or write missing links.
- `okf graph <bundle> -o graph.html` to eyeball the link structure.
