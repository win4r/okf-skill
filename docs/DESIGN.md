# Design rationale

## Principles

1. **Bias toward acceptance.** OKF's spec is *permissive*: §9 enumerates things consumers MUST
   NOT reject for. Over-rejecting a conformant bundle is the cardinal sin, so the validator only
   hard-fails the literal §9 clauses and the zero-dependency parser **fails open** on any
   well-formed structure it doesn't model.
2. **One canonical, reproducible verdict.** Conformance must not depend on whether PyYAML is
   installed. The bundled mini-parser is the single source of truth at runtime (no third-party
   imports); a dev-only CI test asserts its accept/reject verdict matches PyYAML on real bundles.
3. **One shared core.** `okf_core` (parse + model, *no policy*) drives the validator, index
   generator, context selector, graph, and migrator. Reserved-file exclusion, concept-id mapping,
   and link handling are therefore identical everywhere — eliminating the class of bug where a
   visualizer and a validator disagree about what a bundle contains.
4. **Progressive disclosure, twice.** At packaging level (lean SKILL.md → references/scripts by
   path) and at runtime (`okf context` returns only relevant concepts; the skill forbids
   whole-bundle dumps).

## The three tiers

| Tier | Meaning | Affects conformance? | Affects exit code? |
|------|---------|----------------------|--------------------|
| ERROR (`E*`) | literal §9 violation | yes | exit 1 |
| WARNING (`W*`) | spec recommendation / MUST-NOT-reject item | no | only with `--strict` |
| QUALITY (`Q*`) | opt-in project house-style | no | never |

`conformant := (no errors)`. Keeping the tiers separate means "OKF-valid" always means exactly
§9 — a team can raise its own bar (`--profile strict`, `.okf.yml`, `--pedantic`) without
redefining what conformance means for everyone else.

## Boundary calls (and why)

Each of these *could* be argued either way; we cite the clause and make the lenient choice the
default, with an opt-in for the strict reading.

- **`E008` log date is an ERROR.** §7 says date headings MUST be ISO 8601, and §9.3 says reserved
  files MUST follow §6/§7. So a date-shaped non-ISO heading is a genuine conformance violation —
  the gap both reference skills left as a warning. A tight `\d+[-/]\d+[-/]\d+` probe prevents
  false-flagging prose like `## 2026 roadmap`.
- **Relative links are NOT warned by default (`Q009`, opt-in).** §5.1 *recommends* absolute
  `/...` links, but every official sample bundle uses relative links and the reference producer
  bans leading `/`. Default-warning would spray noise across real bundles.
- **Root-index extra key is a WARNING (`W010`), not an error.** §11 permits only `okf_version`
  there, but §9 also says "tolerate unknown keys"; we resolve the tension toward leniency and
  expose `--pedantic` for the maximalist reading.
- **`type` is the only hard-required field.** The official write-guard requires four; the spec
  requires one. We follow the spec and demote `title`/`description`/`timestamp` to warnings.
- **Default-ignore repo housekeeping** (`README.md`, `LICENSE.md`, …) so a repo's README isn't
  flagged as a malformed concept. `--no-default-ignores` restores the strict spec letter.

## Edge cases the validator handles

empty file → `E001`; `---\n---` → `E004` (empty mapping, no type); top-level list/scalar
frontmatter → `E003`; BOM + CRLF tolerated; multi-line folded plain scalars and `|`/`>` block
scalars parsed (not false-`E003`); col-0 block lists (`yaml.safe_dump` style) and indented block
lists; `type` as number/bool/list → `E005`; links inside fenced code ignored; image/anchor/
external links skipped; `../` escaping the bundle root → `W015` and never stat-ed outside; non-
`.md` files ignored; case-insensitive concept-id collisions → `Q008`.
