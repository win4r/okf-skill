"""okf_migrate — convert plain Markdown / wiki notes into a conformant OKF bundle.

For each Markdown file it: ensures YAML frontmatter with a non-empty ``type``; infers
``title`` (frontmatter → first H1 → filename), ``description`` (first paragraph), and
``timestamp`` (file mtime); and rewrites ``[[wikilinks]]`` into bundle-relative Markdown
links resolved against the other notes. It then generates a root index.md and a log.md.

Modes: dry-run (default, report only), ``--out DIR`` (write a new bundle), or ``--write``
(transform in place).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import okf_core as core

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
H1_RE = re.compile(r"^#\s+(.*\S)\s*$", re.MULTILINE)
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _now_iso_from_mtime(path: str) -> str:
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class FileReport:
    rel: str
    type_added: bool = False
    title: str = ""
    wikilinks_converted: int = 0
    wikilinks_unresolved: List[str] = field(default_factory=list)


@dataclass
class MigrationPlan:
    files: List[FileReport] = field(default_factory=list)
    generated_index: bool = False
    generated_log: bool = False

    def summary(self) -> str:
        total = len(self.files)
        conv = sum(f.wikilinks_converted for f in self.files)
        unres = sum(len(f.wikilinks_unresolved) for f in self.files)
        added = sum(1 for f in self.files if f.type_added)
        lines = [
            f"Migration plan: {total} note(s)",
            f"  type frontmatter added: {added}",
            f"  wikilinks converted:    {conv}",
            f"  wikilinks unresolved:   {unres}",
            f"  generated index.md:     {self.generated_index}",
            f"  generated log.md:       {self.generated_log}",
        ]
        for f in self.files:
            tag = " [+type]" if f.type_added else ""
            extra = f"  ({f.wikilinks_converted} links)" if f.wikilinks_converted else ""
            lines.append(f"   - {f.rel}{tag}{extra}")
            for u in f.wikilinks_unresolved:
                lines.append(f"       unresolved wikilink: [[{u}]]")
        return "\n".join(lines)


def _first_paragraph(body: str) -> str:
    in_fence = False
    para: List[str] = []
    for line in body.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        s = line.strip()
        if not s:
            if para:
                break
            continue
        if s.startswith("#") or s.startswith("|") or s.startswith(">"):
            if para:
                break
            continue
        para.append(s)
    text = " ".join(para)
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text).strip()


def _collect_slugmap(src: str) -> Dict[str, str]:
    """Map slug(basename) and slug(title) -> rel path (posix) for wikilink resolution."""
    slugmap: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            if fn in ("index.md", "log.md"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            base = fn[:-3]
            slugmap.setdefault(slugify(base), rel)
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    text = fh.read()
                split = core.split_frontmatter(text)
                m = H1_RE.search(split.body)
                if m:
                    slugmap.setdefault(slugify(m.group(1)), rel)
            except Exception:
                pass
    return slugmap


CODE_SPAN_RE = re.compile(r"(`+)(?:.*?)\1")


def _escaped(line: str, idx: int) -> bool:
    """True if the char at idx is preceded by an odd number of backslashes (CommonMark escape)."""
    bs = 0
    j = idx - 1
    while j >= 0 and line[j] == "\\":
        bs += 1
        j -= 1
    return bs % 2 == 1


def _sub_outside_code(line: str, subfn) -> str:
    """Apply subfn to the parts of `line` that are NOT inside an inline code span (`...`).

    A backtick run escaped by a backslash (``\\``) is literal text per CommonMark, so it does
    not open a code span and its content is still converted.
    """
    out, pos = [], 0
    for m in CODE_SPAN_RE.finditer(line):
        if m.start() < pos or _escaped(line, m.start()):
            continue  # overlaps an emitted span, or the opening backtick is escaped -> not a span
        out.append(subfn(line[pos:m.start()]))
        out.append(m.group(0))  # genuine code span kept verbatim
        pos = m.end()
    out.append(subfn(line[pos:]))
    return "".join(out)


def convert_wikilinks(body: str, slugmap: Dict[str, str], report: FileReport) -> str:
    out_lines: List[str] = []
    in_fence = False

    def repl(m):
        inner = m.group(1).strip()
        alias = None
        if "|" in inner:
            target, alias = inner.split("|", 1)
        else:
            target = inner
        target = target.strip()
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
            anchor = "#" + slugify(anchor)
        label = (alias or target).strip()
        rel = slugmap.get(slugify(target))
        if rel:
            report.wikilinks_converted += 1
            return f"[{label}](/{rel}{anchor})"
        report.wikilinks_unresolved.append(target)
        return f"[{label}](/{slugify(target)}.md{anchor})"

    for line in body.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        # Convert wikilinks, but never inside inline code spans (`...`).
        out_lines.append(_sub_outside_code(line, lambda seg: WIKILINK_RE.sub(repl, seg)))
    return "\n".join(out_lines)


def transform_file(src_path: str, rel: str, slugmap: Dict[str, str], default_type: str) -> Tuple[str, FileReport]:
    report = FileReport(rel=rel)
    with open(src_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    split = core.split_frontmatter(text)
    fm: Dict[str, object] = {}
    if split.has_marker and split.terminated:
        parsed, _err = core.parse_frontmatter(split.raw or "")
        if isinstance(parsed, dict):
            fm = dict(parsed)
    body = split.body if split.has_marker else text

    # title
    title = fm.get("title") if isinstance(fm.get("title"), str) else None
    if not title:
        m = H1_RE.search(body)
        title = m.group(1).strip() if m else os.path.basename(rel)[:-3].replace("_", " ").replace("-", " ").title()
    report.title = title

    # type
    if not (isinstance(fm.get("type"), str) and fm["type"].strip()):
        fm["type"] = default_type
        report.type_added = True

    fm.setdefault("title", title)
    if "description" not in fm:
        desc = _first_paragraph(body)
        if desc:
            fm["description"] = desc
    fm.setdefault("timestamp", _now_iso_from_mtime(src_path))

    body = convert_wikilinks(body, slugmap, report)

    # render frontmatter deterministically (preferred field order first) via the shared
    # round-trip-safe emitter (quotes numeric/bool-looking strings, comma-bearing list items).
    order = ["type", "title", "description", "resource", "tags", "timestamp"]
    keys = [k for k in order if k in fm] + [k for k in fm if k not in order]
    fm_lines = []
    for k in keys:
        fm_lines.extend(core.emit_fm(k, fm[k]))
    content = "---\n" + "\n".join(fm_lines) + "\n---\n" + (body if body.startswith("\n") else "\n" + body)
    return content.rstrip() + "\n", report


def run(args) -> int:
    src = os.path.abspath(args.path)
    if not os.path.isdir(src):
        print(f"okf migrate: not a directory: {src}", file=sys.stderr)
        return 2
    dry_run = not (args.write or args.out)
    out_root = src if args.write else (os.path.abspath(args.out) if args.out else None)

    slugmap = _collect_slugmap(src)
    plan = MigrationPlan()
    transformed: List[Tuple[str, str]] = []  # (dest_rel, content)

    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            if fn in ("index.md", "log.md"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            content, report = transform_file(full, rel, slugmap, args.default_type)
            plan.files.append(report)
            transformed.append((rel, content))

    has_root_index = os.path.isfile(os.path.join(src, "index.md"))
    plan.generated_index = not has_root_index or args.write or bool(args.out)
    plan.generated_log = True

    if dry_run:
        print(plan.summary())
        print("\n(dry run — pass --out DIR to write a new bundle, or --write to transform in place)")
        return 0

    assert out_root is not None
    reserved_copied = []
    if out_root != src:
        os.makedirs(out_root, exist_ok=True)
        # Copy non-markdown assets (references/, images) AND existing reserved files
        # (index.md / log.md) verbatim, so hand-authored index/log content is never lost.
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in sorted(filenames):
                if fn.endswith(".md") and fn not in ("index.md", "log.md"):
                    continue  # concepts are written by the transform loop below
                s = os.path.join(dirpath, fn)
                # Never dereference a symlink whose target escapes the source bundle (exfil guard,
                # consistent with load_bundle): copying it would bake external content into the output.
                if os.path.islink(s) and not core.is_within(s, src):
                    continue
                rel = os.path.relpath(s, src)
                d = os.path.join(out_root, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
                if fn in ("index.md", "log.md"):
                    reserved_copied.append(rel.replace(os.sep, "/"))

    for rel, content in transformed:
        dest = os.path.join(out_root, rel)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)

    # root index + log
    title = os.path.basename(out_root.rstrip("/")) or "Knowledge Base"
    index_path = os.path.join(out_root, "index.md")
    if not os.path.isfile(index_path) or args.regenerate_index:
        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write(f'---\nokf_version: "0.1"\n---\n# {title}\n\n'
                     "<!-- Run `okf index . --recursive --write` to populate sections. -->\n")
    log_path = os.path.join(out_root, "log.md")
    if not os.path.isfile(log_path):
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(f"# Update Log\n\n## {_today()}\n* **Creation**: Migrated "
                     f"{len(transformed)} note(s) into OKF.\n")

    print(plan.summary())
    if reserved_copied:
        print("  preserved reserved files:  " + ", ".join(reserved_copied))
    print(f"\nWrote OKF bundle to {out_root}")
    print("Next: `okf index <bundle> --recursive --write` then `okf validate <bundle>`")
    return 0


def add_arguments(parser):
    parser.add_argument("path", help="Source directory of Markdown/wiki notes")
    parser.add_argument("--out", help="Write a new bundle to this directory (leaves source untouched)")
    parser.add_argument("--write", action="store_true", help="Transform the source directory in place")
    parser.add_argument("--default-type", default="Note", help="type for notes without one (default: Note)")
    parser.add_argument("--regenerate-index", action="store_true", help="Overwrite an existing root index.md")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="okf migrate", description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # noqa: BLE001
        print(f"okf migrate: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
