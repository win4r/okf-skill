---
description: Validate OKF v0.1 conformance (hard errors) and lint (warnings) for a bundle
argument-hint: <bundle-path> [--strict] [--profile strict] [--pedantic] [--format json]
allowed-tools: Bash
---

Run the deterministic OKF validator on the bundle at `$ARGUMENTS` (default to the current
directory if no path is given):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" validate $ARGUMENTS
```

Then summarize for the user:
- **Errors** are conformance failures (exit 1) — list each with its code and file, and offer to fix them.
- **Warnings** are spec recommendations — optional; never block conformance.
- **Quality** lints appear only with `--profile strict`/`.okf.yml` — house style, not OKF conformance.

Do not eyeball conformance; the validator's verdict is authoritative. See the `okf` skill's
`references/conformance.md` for what each code means.
