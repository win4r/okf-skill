"""okf_validate — deterministic OKF v0.1 conformance checker + linter.

Two strictly separated tiers:

* **Tier 1 (error)** — a literal violation of OKF v0.1 conformance (SPEC §6). Any error
  makes the bundle non-conformant and yields a non-zero exit.
* **Tier 2 (warning)** — spec recommendations and "MUST NOT reject" items. Advisory only.
* **Tier 3 (quality)** — opt-in project house-style lints (``--profile strict`` / ``.okf.yml``).
  Never affects conformance.

See ``skills/okf/references/conformance.md`` for the full code list and rationale.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import okf_core as core

KNOWN_OKF_VERSIONS = {"0.1"}

# Loose "looks like a numeric date" probe used to decide whether a non-ISO log heading was
# *meant* to be a date (so we warn) versus an ordinary section heading (which we ignore).
DATEISH_RE = re.compile(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b")
LOG_HEADING_RE = re.compile(r"^##\s+(.*\S)\s*$")


# Upstream SPEC section behind each code (the real SPEC.md numbering, NOT this repo's
# digest numbering) so findings cross-reference the canonical spec without confusion.
SPEC_SECTION = {
    "E001": "§9", "E002": "§9", "E003": "§9", "E004": "§9", "E005": "§9",
    "E006": "§9/§6", "E007": "§3", "E008": "§9/§7",
    "W001": "§4", "W002": "§4", "W003": "§4", "W004": "§4", "W005": "§5.3",
    "W007": "§6", "W009": "§7", "W010": "§11", "W011": "§10", "W012": "§3",
    "W013": "§4", "W015": "§5.3",
    "Q001": "project", "Q002": "project", "Q003": "project", "Q004": "project",
    "Q005": "project", "Q007": "safety", "Q008": "portability", "Q009": "§5.1",
}


@dataclass
class Finding:
    severity: str          # "error" | "warning" | "quality"
    code: str
    name: str
    path: str              # rel_path, or "" for bundle-level
    message: str
    line: Optional[int] = None

    @property
    def spec(self) -> str:
        return SPEC_SECTION.get(self.code, "")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.line is None:
            d.pop("line")
        d["spec"] = self.spec
        return d


@dataclass
class ValidationResult:
    bundle_root: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def quality(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "quality"]

    @property
    def conformant(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------- #
# Project config (.okf.yml) for Tier-3
# --------------------------------------------------------------------------- #
@dataclass
class ProjectConfig:
    profile: str = "conformance"
    types: Optional[List[str]] = None
    concrete_types: List[str] = field(default_factory=list)
    description_max_chars: int = 0
    stale_after_days: int = 0

    @classmethod
    def load(cls, bundle_root: str) -> "ProjectConfig":
        path = os.path.join(bundle_root, ".okf.yml")
        if not os.path.isfile(path):
            return cls()
        with open(path, "r", encoding="utf-8") as fh:
            data, _ = core.parse_frontmatter(fh.read())
        data = data or {}
        return cls(
            profile=str(data.get("profile", "conformance")),
            types=list(data["types"]) if isinstance(data.get("types"), list) else None,
            concrete_types=list(data.get("concrete_types") or []),
            description_max_chars=int(data.get("description_max_chars") or 0),
            stale_after_days=int(data.get("stale_after_days") or 0),
        )


# --------------------------------------------------------------------------- #
# Core validation
# --------------------------------------------------------------------------- #
# Soft reserved-file findings promoted to errors under --pedantic (a maximalist reading of
# §9.3). Off by default because the spec's permissive model treats these as tolerable.
PEDANTIC_PROMOTE = {"W009", "W010"}


def validate_bundle(
    bundle: core.Bundle,
    profile: str = "conformance",
    config: Optional[ProjectConfig] = None,
    check_links: bool = True,
    pedantic: bool = False,
) -> ValidationResult:
    res = ValidationResult(bundle_root=bundle.root)
    add = res.findings.append
    cfg = config or ProjectConfig()
    effective_profile = "strict" if (profile == "strict" or cfg.profile == "strict") else "conformance"

    has_root_index = any(d.kind == "index" and d.is_root_index for d in bundle.documents)
    if not has_root_index:
        add(Finding("warning", "W007", "missing-root-index", "",
                    "Bundle root has no index.md (recommended for progressive disclosure)."))

    for doc in bundle.documents:
        if doc.decode_error:
            add(Finding("error", "E007", "file-not-utf8", doc.rel_path,
                        "File is not valid UTF-8."))
            continue
        if doc.kind == "concept":
            _check_concept(doc, bundle, res, effective_profile, cfg, check_links)
        elif doc.kind == "index":
            _check_index(doc, res)
        elif doc.kind == "log":
            _check_log(doc, res)

    if effective_profile == "strict":
        _check_duplicate_ids(bundle, res)

    if pedantic:
        for f in res.findings:
            if f.code in PEDANTIC_PROMOTE:
                f.severity = "error"

    return res


def _check_duplicate_ids(bundle: core.Bundle, res: ValidationResult):
    seen: Dict[str, List[str]] = {}
    for doc in bundle.concepts:
        seen.setdefault(doc.concept_id.lower(), []).append(doc.rel_path)
    for lower, paths in seen.items():
        if len(paths) > 1:
            res.findings.append(Finding("quality", "Q008", "duplicate-concept-id", paths[0],
                                        f"Concept id collides case-insensitively with: {paths[1:]} "
                                        "(breaks on macOS/Windows)."))


def _check_concept(doc, bundle, res, profile, cfg, check_links):
    add = res.findings.append
    if not doc.fm.has_marker:
        add(Finding("error", "E001", "frontmatter-missing", doc.rel_path,
                    "Concept document has no YAML frontmatter block."))
        return
    if not doc.fm.terminated:
        add(Finding("error", "E002", "frontmatter-unterminated", doc.rel_path,
                    "Frontmatter opening '---' has no closing '---'."))
        return
    if doc.fm_error or doc.frontmatter is None:
        add(Finding("error", "E003", "frontmatter-unparseable", doc.rel_path,
                    f"Frontmatter is not parseable YAML: {doc.fm_error or 'unknown error'}."))
        return

    fm = doc.frontmatter
    if "type" not in fm:
        add(Finding("error", "E004", "type-missing", doc.rel_path,
                    "Required 'type' field is absent from frontmatter."))
    else:
        t = fm["type"]
        # `type` must be a non-empty STRING (SPEC §9). An unquoted YAML int/float/bool
        # (type: 5 / true / 1.5) is not a string; a quoted "5" parses as str and is fine.
        if (t is None or isinstance(t, (list, dict, bool, int, float))
                or (isinstance(t, str) and not t.strip())):
            add(Finding("error", "E005", "type-empty", doc.rel_path,
                        "'type' must be a non-empty string."))

    # ---- Tier 2 warnings ----
    if "title" not in fm:
        add(Finding("warning", "W001", "missing-title", doc.rel_path, "No 'title' (recommended)."))
    if "description" not in fm:
        add(Finding("warning", "W002", "missing-description", doc.rel_path, "No 'description' (recommended)."))
    if "timestamp" not in fm:
        add(Finding("warning", "W003", "missing-timestamp", doc.rel_path, "No 'timestamp' (recommended)."))
    elif not core.is_iso8601(fm.get("timestamp")):
        add(Finding("warning", "W004", "timestamp-not-iso8601", doc.rel_path,
                    f"'timestamp' is not ISO 8601: {fm.get('timestamp')!r}."))
    if "tags" in fm and not _is_str_list(fm["tags"]):
        add(Finding("warning", "W013", "tags-not-list", doc.rel_path,
                    "'tags' should be a YAML list of strings."))
    if not doc.body.strip():
        add(Finding("warning", "W012", "empty-body", doc.rel_path, "Concept has an empty body."))

    if check_links:
        _check_links(doc, bundle, res)

    # ---- Tier 3 quality (opt-in) ----
    if profile == "strict":
        _check_quality(doc, bundle, res, cfg)


def _check_links(doc, bundle, res):
    add = res.findings.append
    for link in doc.links:
        if link.is_external or link.is_anchor_only or not link.anchorless:
            continue
        target = link.anchorless
        if link.is_absolute:
            resolved = os.path.normpath(os.path.join(bundle.root, target.lstrip("/")))
        else:
            base_dir = os.path.dirname(doc.path)
            resolved = os.path.normpath(os.path.join(base_dir, target))
        # Clamp traversal: a link resolving outside the bundle root (after following any
        # symlinks) is treated as escaping and is NEVER stat-ed outside the root. Using
        # realpath containment also fixes the lexical `..`-prefix false positive (a real
        # in-bundle dir literally named e.g. '..notes' is correctly inside the root).
        if not core.is_within(resolved, bundle.root):
            add(Finding("warning", "W015", "link-escapes-bundle", doc.rel_path,
                        f"Link '{link.target}' resolves outside the bundle root.", line=link.line))
            continue
        if not os.path.exists(resolved):
            add(Finding("warning", "W005", "broken-link", doc.rel_path,
                        f"Link target does not exist: {link.target}", line=link.line))
    # NOTE: relative-vs-absolute link form is NOT a default warning — the entire official
    # OKF corpus uses relative links. It is the opt-in Q009 lint (see _check_quality).


def _check_index(doc, res):
    add = res.findings.append
    if not doc.fm.has_marker:
        return
    if not doc.is_root_index:
        add(Finding("error", "E006", "index-has-frontmatter", doc.rel_path,
                    "A non-root index.md must not contain frontmatter."))
        return
    # root index.md: only okf_version is permitted
    fm = doc.frontmatter or {}
    extra = [k for k in fm.keys() if k != "okf_version"]
    if extra:
        add(Finding("warning", "W010", "root-index-extra-frontmatter", doc.rel_path,
                    f"Root index.md frontmatter should only carry 'okf_version'; extra keys: {extra}."))
    if "okf_version" in fm:
        ver = str(fm["okf_version"])
        if ver not in KNOWN_OKF_VERSIONS:
            add(Finding("warning", "W011", "okf-version-unknown", doc.rel_path,
                        f"Declared okf_version {ver!r} is not recognized (known: {sorted(KNOWN_OKF_VERSIONS)})."))


def _check_log(doc, res):
    add = res.findings.append
    dates: List[str] = []
    for lineno, line in enumerate(doc.text.split("\n"), start=1):
        m = LOG_HEADING_RE.match(line)
        if not m:
            continue
        heading = m.group(1).strip()
        # Examine only the LEADING token: '## 2026-05-01 Sprint planning' is a valid ISO
        # date entry with an annotation (a mainstream changelog style) and must be accepted.
        first = heading.split()[0] if heading.split() else ""
        if core.is_iso_date(first):
            dates.append(first)
        elif DATEISH_RE.match(first) and re.search(r"\d{4}", first):
            # §7: log date headings MUST use ISO 8601 -> §9.3 conformance error (E008). The
            # 4-digit-year requirement avoids false-flagging numeric prose like '## 3-2-1 launch'.
            add(Finding("error", "E008", "log-date-not-iso", doc.rel_path,
                        f"Log date heading '{heading}' is not ISO 8601 (YYYY-MM-DD).", line=lineno))
    if dates and dates != sorted(dates, reverse=True):
        add(Finding("warning", "W009", "log-not-newest-first", doc.rel_path,
                    "Log date headings are not in newest-first order."))


SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")


def _check_quality(doc, bundle, res, cfg: ProjectConfig):
    add = res.findings.append
    fm = doc.frontmatter or {}
    t = fm.get("type")

    # Q007: path segments outside the safe charset (mirrors the reference paths.py guard).
    for seg in doc.rel_path.split("/"):
        if seg and not SAFE_SEGMENT_RE.match(seg):
            add(Finding("quality", "Q007", "unsafe-path-segment", doc.rel_path,
                        f"Path segment {seg!r} is outside the portable charset [A-Za-z0-9_][A-Za-z0-9_.-]*."))
            break

    # Q009: relative concept links (spec §5.1 recommends absolute). Opt-in only — real
    # bundles use relative links, so this must never be a default warning.
    for link in doc.links:
        if (not link.is_external and not link.is_anchor_only
                and link.anchorless.endswith(".md") and not link.is_absolute):
            add(Finding("quality", "Q009", "relative-link", doc.rel_path,
                        f"Relative link '{link.target}'; absolute '/...' links are recommended (§5.1).",
                        line=link.line))
    if cfg.types is not None and isinstance(t, str) and t not in cfg.types:
        add(Finding("quality", "Q001", "type-not-in-registry", doc.rel_path,
                    f"type {t!r} is not in the project registry {cfg.types}."))
    desc = fm.get("description")
    if cfg.description_max_chars and isinstance(desc, str) and len(desc) > cfg.description_max_chars:
        add(Finding("quality", "Q002", "description-too-long", doc.rel_path,
                    f"description is {len(desc)} chars (> {cfg.description_max_chars})."))
    # orphan: no outbound concept links and no inbound concept links
    outbound = any(
        (l.is_absolute or (not l.is_external and not l.is_anchor_only)) and l.anchorless.endswith(".md")
        for l in doc.links
    )
    inbound = _has_inbound(doc, bundle)
    if not outbound and not inbound:
        add(Finding("quality", "Q003", "orphan-concept", doc.rel_path,
                    "Concept has no inbound or outbound concept links."))
    if isinstance(t, str) and t in cfg.concrete_types and not fm.get("resource"):
        add(Finding("quality", "Q004", "missing-resource", doc.rel_path,
                    f"Concrete type {t!r} has no 'resource' URI."))


def _has_inbound(target_doc, bundle) -> bool:
    target_rel = target_doc.rel_path
    for other in bundle.concepts:
        if other.rel_path == target_rel:
            continue
        for link in other.links:
            if link.is_external or link.is_anchor_only:
                continue
            t = link.anchorless
            if link.is_absolute:
                resolved = posixpath.normpath(t.lstrip("/"))
            else:
                base = posixpath.dirname(other.rel_path)
                resolved = posixpath.normpath(posixpath.join(base, t))
            if resolved == target_rel:
                return True
    return False


def _is_str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


# --------------------------------------------------------------------------- #
# Output rendering
# --------------------------------------------------------------------------- #
_ICON = {"error": "✗", "warning": "▲", "quality": "•"}
_COLOR = {"error": "\033[31m", "warning": "\033[33m", "quality": "\033[36m"}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def render_human(res: ValidationResult, use_color: bool) -> str:
    def c(s, col):
        return f"{col}{s}{_RESET}" if use_color else s

    lines: List[str] = []
    by_path: Dict[str, List[Finding]] = {}
    for f in res.findings:
        by_path.setdefault(f.path, []).append(f)

    for path in sorted(by_path, key=lambda p: (p == "", p)):
        header = path if path else "(bundle)"
        lines.append(c(header, _BOLD))
        for f in sorted(by_path[path], key=lambda x: (x.severity != "error", x.code, x.line or 0)):
            loc = f":{f.line}" if f.line else ""
            icon = c(_ICON[f.severity], _COLOR[f.severity])
            spec = (" " + c("[" + f.spec + "]", _DIM)) if f.spec else ""
            lines.append(f"  {icon} {c(f.code, _COLOR[f.severity])} {f.name}{spec}{loc}: {f.message}")
        lines.append("")

    status = "CONFORMANT" if res.conformant else "NON-CONFORMANT"
    status_col = "\033[32m" if res.conformant else "\033[31m"
    summary = (
        f"{c(status, status_col + _BOLD if use_color else '')}  "
        f"{len(res.errors)} error(s), {len(res.warnings)} warning(s)"
    )
    if res.quality:
        summary += f", {len(res.quality)} quality lint(s)"
    lines.append(summary)
    return "\n".join(lines)


def render_json(res: ValidationResult) -> str:
    payload = {
        "bundle": res.bundle_root,
        "conformant": res.conformant,
        "summary": {
            "errors": len(res.errors),
            "warnings": len(res.warnings),
            "quality": len(res.quality),
        },
        "findings": [f.to_dict() for f in res.findings],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# CLI entry
# --------------------------------------------------------------------------- #
def run(args) -> int:
    if not os.path.isdir(args.path):
        # A missing/typo'd path is a tool-usage error (exit 2), NOT a vacuously-conformant
        # empty bundle (exit 0) — otherwise a path typo silently passes a CI gate.
        raise NotADirectoryError("bundle path is not a directory: %s" % args.path)
    bundle = core.load_bundle(
        args.path,
        default_ignores=not args.no_default_ignores,
        extra_ignores=args.ignore or [],
    )
    cfg = ProjectConfig.load(bundle.root)
    res = validate_bundle(
        bundle,
        profile=args.profile,
        config=cfg,
        check_links=not args.no_links,
        pedantic=args.pedantic,
    )
    if args.format == "json":
        print(render_json(res))
    else:
        use_color = sys.stdout.isatty() and not args.no_color
        print(render_human(res, use_color))

    if res.errors:
        return 1
    if args.strict and res.warnings:
        return 1
    return 0


def add_arguments(parser):
    parser.add_argument("path", help="Path to the OKF bundle root")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    parser.add_argument("--profile", choices=["conformance", "strict"], default="conformance",
                        help="conformance = spec errors+warnings; strict = also Tier-3 quality lints")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero if there are warnings (not just errors)")
    parser.add_argument("--pedantic", action="store_true",
                        help="Promote soft reserved-file warnings (W009/W010) to errors (maximalist §9.3)")
    parser.add_argument("--no-links", action="store_true", help="Skip cross-link checking")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--no-default-ignores", action="store_true",
                        help="Treat README.md/LICENSE.md/etc. as concepts (strict spec letter)")
    parser.add_argument("--ignore", action="append", metavar="GLOB",
                        help="Additional path globs to skip (repeatable)")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="okf validate", description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # noqa: BLE001
        print(f"okf validate: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
