---
description: Pull only the relevant OKF concepts for a task (progressive disclosure, no bundle dump)
argument-hint: <bundle-path> "<task topic>" [--mode summary|full|headers] [--max N]
allowed-tools: Bash
---

Assemble a compact OKF context pack for `$ARGUMENTS` instead of reading the whole bundle:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/okf.py" context $ARGUMENTS
```

- with a query → ranks concepts by relevance, returns the top matches plus their 1-hop
  neighbors as frontmatter summaries (`--mode full` adds bodies; `--mode headers` is leanest).
- with no query → prints a lightweight outline (the map, without the contents).

Use this in **consume/maintain** work so only task-relevant knowledge enters context — this is
OKF's whole point. Never paste an entire bundle into the conversation.
