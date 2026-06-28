---
description: Convert a folder of Markdown / wiki notes into a conformant OKF bundle
argument-hint: <src-dir> --out <bundle-dir>
allowed-tools: Bash, Read, Edit
---

Migrate the notes at `$ARGUMENTS` into an OKF bundle. First do a dry run to preview the plan,
then write the bundle, generate indexes, and validate:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" migrate $ARGUMENTS
```

If the user passed `--out <dir>` (or `--write`), follow up with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" index <out-dir> --recursive --write
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" validate <out-dir>
```

Report wikilinks converted and any unresolved ones. **Never invent data**: if a note's `type`
is unclear, leave the default `Note` (or a visible TODO) rather than guessing a precise type.
See the `okf` skill's `references/migration.md` for Obsidian/Notion/CSV field mappings.
