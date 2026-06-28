---
description: Generate or refresh index.md directory listings from concept frontmatter
argument-hint: <bundle-path> [--recursive] [--write | --check]
allowed-tools: Bash
---

Regenerate OKF `index.md` files for the bundle at `$ARGUMENTS`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" index $ARGUMENTS
```

- no flag → print the proposed index to stdout (preview).
- `--recursive --write` → write an index.md in every directory (maintenance).
- `--check` → exit 1 if any index.md is stale (use in CI / pre-commit).

Generation is deterministic and offline: titles/descriptions come straight from each concept's
frontmatter; the root index keeps its `okf_version`.
