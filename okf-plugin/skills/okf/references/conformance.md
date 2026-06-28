# OKF Conformance vs. Lint — the two-tier model

This is the exact contract the deterministic validator (`scripts/okf.py validate`) implements.
The central design rule:

> **Tier 1 (ERROR) = a literal violation of OKF v0.1 conformance (upstream SPEC §9).**
> **Tier 2 (WARNING) = a spec recommendation or a "MUST NOT reject" item. NEVER a conformance failure.**
> **Tier 3 (QUALITY) = opt-in project house-style. Never affects conformance or exit code.**

Section numbers below are the **upstream `SPEC.md`** numbering (not this repo's
[spec-digest.md](spec-digest.md), which condenses the same rules under its own headings):
`§3` document/UTF-8 · `§4` frontmatter fields · `§5` cross-links (`§5.1` absolute recommended,
`§5.3` broken links tolerated) · `§6` index files · `§7` log files · `§8` citations ·
`§9` conformance · `§10` versioning · `§11` `okf_version` in root index.

**The cardinal rule: bias toward acceptance.** Over-rejection violates §9's permissive model and
is worse than a missed lint. Everything the spec says consumers MUST NOT reject for is *forbidden*
from being a Tier-1 error.

Exit codes: `0` conformant (no errors) · `1` errors present (or warnings present with `--strict`) ·
`2` tool failure. `--strict` promotes warnings to a non-zero exit; quality lints never affect it.

---

## Tier 1 — Conformance ERRORS

A bundle with any of these is **non-conformant**. Each maps to a §9 clause.

| Code | Name | Condition | SPEC |
|------|------|-----------|------|
| `E001` | `frontmatter-missing` | A concept (non-reserved `.md`) does not begin with a `---` frontmatter block. | §9 |
| `E002` | `frontmatter-unterminated` | An opening `---` exists but there is no closing `---`. | §9 |
| `E003` | `frontmatter-unparseable` | The block is not a YAML **mapping** (a bare sequence/scalar, or content with no top-level `key:`). Reserved for genuinely non-mapping frontmatter — the parser fails *open* on anything well-formed. | §9 |
| `E004` | `type-missing` | Frontmatter parses as a mapping but has no `type` key. OKF's single most important rule. | §9 |
| `E005` | `type-empty` | `type` is present but null, empty/whitespace-only, or not a scalar string. | §9 |
| `E006` | `index-has-frontmatter` | A **non-root** `index.md` contains a frontmatter block (reserved files carry none). | §9 / §6 |
| `E007` | `file-not-utf8` | A `.md` file is not decodable as UTF-8. | §3 |
| `E008` | `log-date-not-iso` | A `log.md` `##` heading's **leading token** is date-shaped with a 4-digit year (e.g. `05/22/2026`) but not a valid `YYYY-MM-DD`. §7's explicit MUST, enforced via §9 rule 3 — the gap both reference skills left as a warning. A valid ISO date followed by a title (`## 2026-05-01 Sprint planning`) is **accepted**; numeric prose (`## 3-2-1 launch`) is ignored. | §9 / §7 |

**Concept vs reserved.** `index.md` and `log.md` are reserved (never checked for `type`). Every
other `.md` is a concept. **Default-ignored** repo housekeeping (not concepts): `README.md`,
`LICENSE.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` — use
`--no-default-ignores` for the strict spec letter, or `--ignore GLOB` to extend.

---

## Tier 2 — Lint WARNINGS (spec-recommended; never break conformance)

| Code | Name | Condition | SPEC |
|------|------|-----------|------|
| `W001` | `missing-title` | Concept has no `title`. | §4 |
| `W002` | `missing-description` | Concept has no `description`. | §4 |
| `W003` | `missing-timestamp` | Concept has no `timestamp`. | §4 |
| `W004` | `timestamp-not-iso8601` | `timestamp` is not an ISO 8601 date/datetime. | §4 |
| `W005` | `broken-link` | A bundle-relative link points at a file that does not exist. **Always** a warning — §5.3 says consumers MUST tolerate broken links (may be not-yet-written knowledge). | §5.3 |
| `W007` | `missing-root-index` | The bundle root has no `index.md`. | §6 |
| `W009` | `log-not-newest-first` | `log.md` date headings are not in descending order (softer than the ISO MUST). | §7 |
| `W010` | `root-index-extra-frontmatter` | Root `index.md` frontmatter carries keys other than `okf_version`. A deliberate boundary call: a warning, aligning with §9's "tolerate unknown keys." | §11 |
| `W011` | `okf-version-unknown` | Declared `okf_version` is not a recognized `<major>.<minor>` (known: `0.1`). | §10 |
| `W012` | `empty-body` | Concept has valid frontmatter but an empty Markdown body. | §3 |
| `W013` | `tags-not-list` | `tags` is a scalar string instead of a YAML list. (The real `stackoverflow` bundle does this — warn, never reject.) | §4 |
| `W015` | `link-escapes-bundle` | A link resolves (after following symlinks, via realpath containment) outside the bundle root. Treated as broken; never stat-ed outside the root (safety). | §5.3 |

> **Why `relative-link` is NOT a default warning.** §5.1 *recommends* absolute `/...` links, but the
> entire official corpus (ga4 / crypto_bitcoin / stackoverflow) uses **relative** links and the
> reference producer bans leading `/`. Default-warning would spray noise across every real bundle,
> so it is the opt-in quality lint **`Q009`** instead.

---

## Tier 3 — Project-quality lints (opt-in; NEVER affect conformance)

Enabled only with `--profile strict` or a project `.okf.yml`. House style, never OKF conformance.

| Code | Name | Condition |
|------|------|-----------|
| `Q001` | `type-not-in-registry` | `type` is not in `.okf.yml` `types:`. |
| `Q002` | `description-too-long` | `description` exceeds `description_max_chars`. |
| `Q003` | `orphan-concept` | Concept has neither inbound nor outbound concept links. |
| `Q004` | `missing-resource` | A `concrete_types:` concept lacks a `resource`. |
| `Q005` | `stale-timestamp` | `timestamp` older than `stale_after_days`. |
| `Q007` | `unsafe-path-segment` | A path segment is outside the portable charset `[A-Za-z0-9_][A-Za-z0-9_.-]*`. |
| `Q008` | `duplicate-concept-id` | Two concept ids collide case-insensitively (breaks on macOS/Windows). |
| `Q009` | `relative-link` | A concept link is relative rather than absolute (§5.1 recommends absolute). |

`.okf.yml` (optional, bundle root):
```yaml
profile: strict
types: [Dataset, Table, View, Metric, Playbook, Glossary Term]
concrete_types: [Table, View, Dataset]
description_max_chars: 160
stale_after_days: 365
```

### `--pedantic`
A maximalist reading of §9 rule 3: promotes the soft reserved-file warnings `W009` and `W010` to
**errors**. Off by default because the spec's permissive model treats them as tolerable. Every
boundary call here is deliberate and cites its clause — reasonable readers of §9.3 may want the
stricter bar, and `--pedantic` gives it to them without changing what "OKF-valid" means by default.

---

## Why this split matters

- A producer migrating messy notes can reach **conformant** (zero Tier-1 errors) fast, then burn
  down Tier-2 warnings over time.
- A consumer can trust "conformant" means exactly §9's clauses — no more, no less.
- Teams wanting a higher bar opt into Tier-3 / `--pedantic` without redefining "OKF-valid."
