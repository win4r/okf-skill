---
name: okf
description: >-
  Create, maintain, validate, migrate, and visualize Open Knowledge Format (OKF) bundles —
  directories of Markdown files with YAML frontmatter that any agent or human can consume.
  Use when the user says "document this in OKF", "make this folder OKF-conformant", "validate
  / lint an OKF bundle", "update the knowledge bundle", "capture this as a concept", "convert
  these notes / wiki / Obsidian vault to OKF", "build an LLM-wiki / knowledge base for agents",
  "visualize the bundle", or whenever working in a repo that contains an OKF bundle (a tree of
  .md files with `type:` frontmatter, often under a dir with an index.md + log.md).
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Open Knowledge Format (OKF)

OKF is a **format, not a platform**: a *bundle* is a directory tree of UTF-8 Markdown files
with YAML frontmatter. One concept = one file; the file path (minus `.md`) is its identity.
No accounts, SDKs, or cloud services are involved. Work Git-natively with plain files.

## Ground truth — read before non-trivial work

Be conformant **with the spec, not your memory of it.** Before authoring or judging
conformance, read:

- [`references/spec-digest.md`](references/spec-digest.md) — the rules, condensed.
- [`references/conformance.md`](references/conformance.md) — exactly what is an ERROR vs a
  WARNING vs an opt-in quality lint.
- [`references/migration.md`](references/migration.md) — Markdown/Notion/Obsidian/CSV → OKF.

These map every rule to its upstream `SPEC.md` section. When in doubt, the upstream SPEC wins.

## The one hard rule

> Every non-reserved `.md` (a **concept**) MUST have a parseable YAML frontmatter block whose
> `type` is a non-empty string.

`type` is the **only** required field. `title`, `description`, `resource`, `tags`, `timestamp`
are recommended. `index.md` and `log.md` are reserved (no `type`).

## The toolchain — never eyeball conformance

All tools are one zero-dependency CLI (pure Python 3.8+, no `pip install`). Run via:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" <command> ...
```

If `$CLAUDE_PLUGIN_ROOT` is unset, first resolve the path and confirm `okf.py` exists before
shelling out. Commands: `validate`, `new`, `index`, `context`, `graph`, `migrate`
(see `okf.py <command> --help`). **Conformance is decided by the validator, not by you.**

## Modes

### Create
1. Read the spec digest. Pick the source (code, docs, a database schema, manual knowledge).
2. Scaffold: `okf new bundle <path>` then `okf new concept <id> --bundle <path> --type <T> …`,
   or copy [`templates/`](templates/). Fill `title`/`description`; add `resource` only for a
   real asset; use conventional body headings (`# Schema`, `# Examples`, `# Citations`).
3. Cross-link concepts with Markdown links (relative `../x.md` or absolute `/x.md` — both are
   accepted; the corpus uses relative). A link asserts a relationship; prose says what kind.
4. `okf index <bundle> --recursive --write` to generate index.md files; keep `okf_version` in
   the root index. Add a `log.md`.
5. `okf validate <bundle>` and **fix every error**. Warnings are optional polish.

### Maintain
Find the concepts a change affects (by `resource`, path, or topic — use `okf context`). Update
the body and bump `timestamp`. Fix or add links. Prefer marking a concept deprecated in its
body over deleting it. Regenerate indexes (`okf index … --write`), append a dated entry to
`log.md` (newest first, `## YYYY-MM-DD`), then re-validate.

### Consume — progressive disclosure (do NOT dump the bundle)
Never read every file. Start at the root `index.md`, or run
`okf context <bundle> "<task topic>"` to pull only the relevant concepts (+1-hop neighbors) as
a compact pack. Follow only task-relevant links. Treat a broken link as not-yet-written
knowledge, not an error. Switch to **Maintain** when you learn something durable.

### Migrate
`okf migrate <src-dir> --out <bundle>` converts a folder of plain Markdown/wiki notes into a
bundle (infers `type`/`title`/`description`/`timestamp`, rewrites `[[wikilinks]]`), then
`okf index … --write` and `okf validate`. See [`references/migration.md`](references/migration.md)
for Notion/Obsidian/CSV field mappings. **Never invent data** — leave a visible TODO instead.

### Visualize
`okf graph <bundle> -o graph.html` writes a single self-contained, **offline** interactive
graph (no CDN, no backend). `--format mermaid` or `--format json` for embedding/scripting.

## Guardrails (the spec's permissive model)

- Never fabricate facts, schemas, or citations. Ask or leave a TODO.
- Preserve unknown frontmatter keys and unknown `type` values — never reject them.
- Don't impose a type taxonomy; `type` is free-form (a project may opt into a registry via
  `.okf.yml` + `okf validate --profile strict`).
- Broken links and missing optional fields are tolerated — warnings, never conformance errors.
- Keep concepts minimal by default; add structure only when it earns its place.
