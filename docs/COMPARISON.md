# Comparison against the two reference OKF skills

This document compares the **okf** skill in this repo against the two existing community OKF
skills, and against the official `okf/` reference implementation. It is based on reading the
upstream `SPEC.md` (source of truth), the official `reference_agent` package and sample
bundles, and the full source of both skills.

## TL;DR

Both reference skills are good and got the *philosophy* right (vendor the spec, mandate a
deterministic checker, honor the permissive model). The biggest practical gaps they share are:
(1) the spec's conformance rule 3 (reserved-file structure) has **no teeth** — a non-ISO
`log.md` date is reported conformant; (2) neither has a **correct + zero-dependency** YAML
verdict; (3) neither ships a **deterministic migrate** tool; (4) the visualizers are untested
and CDN-dependent. This skill targets exactly those gaps while preserving what they do well.

---

## 1. scaccogatto/okf-skills

A polished 3-skill plugin (okf / validate / visualize) with a vendored, commit-pinned spec, a
PyYAML-based Python validator, a Cytoscape visualizer, templates, dual distribution, and CI
with a negative self-test.

**Strengths (kept / matched here):**
- Vendors the spec and treats it as ground truth; mandates "never eyeball conformance."
- Real error/warning separation with conventional exit codes and `--json`.
- Excellent progressive disclosure at the packaging level (lean SKILL.md, heavy work in scripts).
- CI **negative/mutation self-test** proving the green check is load-bearing — we adopt this.
- Spec-aware lint tuning (excludes `resource` from recommended-field warnings; fenced-code-aware
  link extraction) — we match this.

**Gaps this skill closes:**
| Gap in scaccogatto | What this skill does |
|---|---|
| §9.3 under-enforced: a non-ISO `log.md` date is a *warning*, so the bundle still reports `conformant:true` | `E008` makes a date-shaped non-ISO log heading a hard **error** (tight regex avoids prose false-positives) |
| Validator **depends on PyYAML**; the conformance verdict differs with/without it (folded `description` → conformant only *with* PyYAML) | Zero-dependency parser is the single canonical verdict; a CI test asserts it matches PyYAML on real bundles + a fuzz set |
| Visualizer has **zero test coverage** (shipped a crash) and loads Cytoscape/marked from a **CDN** (not offline) | Vanilla-JS visualizer with **no CDN/network**, escaped rendering, and golden-output tests |
| No migration tool | `okf migrate` deterministically converts Markdown/wiki notes (incl. `[[wikilinks]]`) |
| `${CLAUDE_SKILL_DIR}` + cross-skill relative fallback path is fragile | One `okf.py` dispatcher under `${CLAUDE_PLUGIN_ROOT}` with a resolved-path guard |
| Empty/zero-concept bundle silently "conformant" | Same (vacuously true) but we emit `W007` for a missing root index |

## 2. fabricioctelles/skills · okf-open-knowledge-format

A single, content-rich SKILL.md (~425 lines) with the vendored spec, worked examples, strong
guardrails, conversion playbooks (Notion/Obsidian/CSV), and a **bash** fallback validator that
defers to an external `okflint` when present.

**Strengths (kept / matched here):**
- Encodes the spec's permissive "consumers MUST NOT reject for…" model as explicit guardrails.
- Genuinely useful conversion playbooks — we carry these into `references/migration.md` and back
  them with a real tool.
- Documented E/W taxonomy and a clean color-coded two-counter output design.

**Gaps this skill closes:**
| Gap in fabricioctelles | What this skill does |
|---|---|
| **Critical:** `validate.sh` crashes (`set -e` + `pipefail` + `grep` no-match) on a file **missing `type`** — OKF's single most important check — printing nothing and skipping the rest | `E004` (type-missing) is a first-class, tested check that never silently skips |
| Unterminated frontmatter (`---` with no closing `---`) **falsely passes** | `E002` detects it before YAML parsing |
| No real YAML parsing (greps `^type:`); invalid YAML / tabs / `type :` mishandled | A real (fail-open) YAML-subset parser |
| Documented warnings W2–W5 (broken links, etc.) are **not implemented** | `W005` broken-link, `W015` escape, etc. are implemented and tested |
| `exit $ERRORS` returns the **error count** (wraps mod 256 → 256 errors = exit 0) | Clean `0/1/2` exit contract |
| Runtime "Output Format" tells the agent to **dump every file's full content** — the opposite of progressive disclosure | `okf context` returns only relevant concepts; the skill forbids whole-bundle dumps |
| Hardcoded Portuguese install prompt; `okflint` gate adds friction | Self-contained zero-dep tool; no install gate, no language assumption |

## 3. Official `okf/` (GoogleCloudPlatform/knowledge-catalog)

Source of truth for the **spec**; the **code** is a producer + visualizer, not a validator.

- `OKFDocument.validate()` requires `type, title, description, timestamp` — **stricter than the
  spec** (only `type` is required). Copying it would over-reject conformant bundles. We treat
  only `type` as a hard error and the other three as warnings.
- The visualizer and index generator skip only `index.md`, so a reserved **`log.md` is rendered
  as a concept node**. Our shared `okf_core` excludes *both* reserved files everywhere.
- The official viewer's edges are relative-only while its in-body link rewriter is absolute-only
  — an asymmetry that breaks clickable nav on its own output. Our graph handles **both** forms.
- Index regeneration calls Gemini for directory descriptions; ours is **fully offline/deterministic**.

## What we deliberately did NOT change

- We kept the permissive model intact. Relative-vs-absolute links are **not** a default warning
  (the entire official corpus uses relative links); it is the opt-in `Q009` lint.
- Boundary calls (root-index extra key = warning; log ordering = warning) match the spec's
  leniency and are each documented with their clause. `--pedantic` exists for maximalist readers.
- We did not add a paid/cloud/LLM dependency anywhere in the shipped tooling.
