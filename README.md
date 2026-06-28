# OKF Skill — a stronger Claude Code skill set for the Open Knowledge Format

A Claude Code plugin for working with **[Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)** v0.1 — Google Cloud's open spec for representing knowledge as a directory of Markdown files with YAML frontmatter (the "LLM-wiki" pattern). It helps you **create, maintain, validate, migrate, and visualize** OKF bundles.

The headline: the official OKF repo ships a *producer* (a Gemini/BigQuery enrichment agent) and an HTML *visualizer*, but **no standalone conformance validator** — the closest thing is a producer write-guard that is actually *stricter* than the spec. This project fills that gap with a **deterministic, zero-dependency validator** that implements the spec's conformance rules exactly and keeps **hard OKF errors strictly separate from optional lint warnings**.

> No Gemini, Google Cloud, BigQuery, paid service, or account required. Pure Python 3.8+ standard library. Plain Markdown, YAML frontmatter, standard Markdown links, Git-friendly.

## Highlights

- **Deterministic, zero-dependency validator** (pure Python 3.8+ standard library) with a strict
  two-tier model: hard OKF v0.1 conformance **errors** are kept separate from optional lint
  **warnings**, plus an opt-in project-quality tier.
- **Bias toward acceptance.** A zero-dependency YAML mini-parser whose accept/reject verdict is
  tested to match PyYAML on real bundles, so it never over-rejects spec-conformant content
  (multi-line folded scalars, scalar `tags`, relative links, unknown `type` values).
- **Full toolchain** behind one `okf.py` CLI: scaffold (`new`), maintain indexes (`index`),
  progressive-disclosure context packs (`context`), an **offline** link-graph visualizer
  (`graph`, no CDN/backend), and Markdown/wiki → OKF migration with `[[wikilink]]` resolution
  (`migrate`).
- **A real skill set:** an `okf` SKILL.md, slash commands, and reference docs, packaged as an
  installable Claude Code plugin.
- **Tested:** parser↔PyYAML equivalence, a negative corpus (one bundle per error code), and CI
  on a Python 3.8 + 3.12 matrix.

## Quickstart

```bash
# 1. Scaffold a bundle and a concept
python3 okf-plugin/scripts/okf.py new bundle my-kb --title "My KB"
python3 okf-plugin/scripts/okf.py new concept tables/orders --bundle my-kb \
    --type "Table" --description "One row per order." --schema

# 2. Generate index.md files and validate
python3 okf-plugin/scripts/okf.py index my-kb --recursive --write
python3 okf-plugin/scripts/okf.py validate my-kb            # exit 0 = conformant

# 3. Pull only the relevant concepts for a task (no whole-bundle dump)
python3 okf-plugin/scripts/okf.py context my-kb "orders revenue"

# 4. Visualize the link graph (single offline HTML)
python3 okf-plugin/scripts/okf.py graph my-kb -o my-kb-graph.html

# 5. Migrate a folder of plain Markdown / wiki notes into OKF
python3 okf-plugin/scripts/okf.py migrate ./notes --out ./notes-okf
```

Everything runs with the standard library — there is nothing to `pip install`. (PyYAML is used
only by the dev test-suite to prove the bundled parser agrees with it.)

## The two-tier model (the whole point)

```
ERROR    → a literal OKF v0.1 conformance violation (SPEC §9). Exit 1.        E001–E008
WARNING  → a spec recommendation / "MUST NOT reject" item. Never blocks.      W001–W015
QUALITY  → opt-in project house-style (--profile strict / .okf.yml).          Q001–Q009
```

A bundle can be **100% conformant and still have many warnings** — and that's fine. The
cardinal rule is **bias toward acceptance**: over-rejecting a spec-conformant bundle (e.g. one
using multi-line folded YAML scalars, scalar `tags`, relative links, or unknown `type` values)
is the worst failure mode, because it violates the spec's permissive consumption model. See
[the conformance reference](okf-plugin/skills/okf/references/conformance.md) for every code.

## Install as a Claude Code plugin

This repo is a plugin marketplace. Add it and install the `okf` plugin:

```
/plugin marketplace add <path-or-git-url-to-this-repo>
/plugin install okf@okf-skill
```

Then the skill auto-activates on OKF work, and these commands are available:
`/okf:validate`, `/okf:new`, `/okf:index`, `/okf:context`, `/okf:graph`, `/okf:migrate`.

## Keep a bundle conformant (pre-commit hook)

To block commits that break OKF conformance or leave indexes stale, drop the shipped hook
template into your bundle repo:

```bash
mkdir -p .githooks
cp okf-plugin/templates/pre-commit .githooks/pre-commit   # then edit OKF_CLI / OKF_BUNDLE
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
```

It runs `okf validate <bundle> --strict` (warnings block too — drop `--strict` to allow them)
and `okf index <bundle> --recursive --check`. This repo dogfoods its own guard via
[`.githooks/pre-commit`](.githooks/pre-commit), which validates the example bundles and runs
the test suite on every commit.

## Repo layout

```
okf-plugin/                      installable Claude Code plugin
├── .claude-plugin/plugin.json
├── skills/okf/
│   ├── SKILL.md                 authoring/maintain/consume brain (progressive disclosure)
│   ├── references/              spec-digest.md · conformance.md · migration.md
│   └── templates/               concept.md · index.md · log.md
├── commands/                    /okf:validate, new, index, context, graph, migrate
├── templates/CLAUDE-okf.md      paste-in soft-mode upkeep snippet
└── scripts/                     zero-dependency toolchain (okf.py dispatcher + modules)
examples/
├── valid/acme-analytics/        golden, --strict-clean showcase bundle
├── valid/permissive-quirks/     conformant DESPITE quirks (proves leniency)
└── invalid/E001…E008/           one minimal bundle per error code (negative corpus)
tests/                           pytest: validator, tools, examples, parser↔PyYAML equivalence
docs/                            DESIGN.md (design rationale + boundary calls)
.github/workflows/ci.yml         3.8 + 3.12 matrix
```

## License

Apache-2.0 (matching the upstream OKF spec). See [LICENSE](LICENSE).
