---
description: Render an OKF bundle's link graph as a self-contained offline HTML (or mermaid/json)
argument-hint: <bundle-path> [-o graph.html] [--format html|mermaid|json]
allowed-tools: Bash
---

Visualize the OKF bundle at `$ARGUMENTS`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" graph $ARGUMENTS
```

Defaults to a single self-contained, **offline** interactive HTML graph (no CDN, no backend) —
nodes are concepts colored by `type`, edges are cross-links (dashed = broken target). Use
`--format mermaid` for a diagram to embed in Markdown, or `--format json` to script against the
node/edge data. Tell the user where the file was written.
