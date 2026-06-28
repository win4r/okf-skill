---
description: Scaffold a new OKF bundle or a new concept document (conformant by construction)
argument-hint: bundle <path> | concept <id> --bundle <path> --type <T>
allowed-tools: Bash
---

Scaffold OKF structure with `$ARGUMENTS`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" new $ARGUMENTS
```

- `new bundle <path>` creates `<path>/index.md` (with `okf_version`) and `log.md`.
- `new concept <id> --bundle <path> --type <T> [--title … --description … --tags a,b --schema]`
  writes a concept whose frontmatter is conformant (non-empty `type`, ISO timestamp).

After scaffolding, run `okf index <bundle> --recursive --write` then `okf validate <bundle>`.
