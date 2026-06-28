"""okf_index — generate or refresh index.md files from concept frontmatter.

An index.md is a progressive-disclosure directory listing. This tool reads the
``title``/``description`` of every concept in a directory (and links to child-directory
indexes) and renders a conventional index.md. Use ``--write`` to maintain a bundle and
``--check`` in CI to fail when an index is stale.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

import okf_core as core


def _title_for(doc: core.Document) -> str:
    fm = doc.frontmatter or {}
    if isinstance(fm.get("title"), str) and fm["title"].strip():
        return fm["title"].strip()
    base = os.path.basename(doc.rel_path)[:-3]
    return base.replace("_", " ").replace("-", " ").title()


def _desc_for(doc: core.Document) -> str:
    fm = doc.frontmatter or {}
    d = fm.get("description")
    return d.strip() if isinstance(d, str) and d.strip() else ""


def _dir_title(dirname: str) -> str:
    if not dirname:
        return "Index"
    return os.path.basename(dirname.rstrip("/")).replace("_", " ").replace("-", " ").title()


def render_index(bundle: core.Bundle, dir_rel: str, okf_version: Optional[str] = None) -> str:
    """Render the index.md body for one directory (dir_rel is posix, '' = root)."""
    is_root = dir_rel == ""
    prefix = "" if is_root else dir_rel + "/"

    # Concepts that live directly in this directory.
    concepts: List[core.Document] = []
    subdirs: Dict[str, Optional[core.Document]] = {}
    for doc in bundle.documents:
        rp = doc.rel_path
        if not rp.startswith(prefix):
            continue
        rest = rp[len(prefix):]
        if "/" not in rest:
            if doc.kind == "concept":
                concepts.append(doc)
        else:
            sub = rest.split("/", 1)[0]
            subdirs.setdefault(sub, None)
            if doc.kind == "index" and rest == f"{sub}/index.md":
                subdirs[sub] = doc

    out: List[str] = []
    if is_root and okf_version:
        out.append("---")
        out.append(f'okf_version: "{okf_version}"')
        out.append("---")
    out.append(f"# {_dir_title(dir_rel)}")
    out.append("")

    if subdirs:
        out.append("## Sections")
        out.append("")
        for sub in sorted(subdirs):
            idx = subdirs[sub]
            desc = ""
            label = _dir_title(sub)
            if idx is not None:
                # use the first body heading text if available; else dir title
                desc = ""
            out.append(f"* [{label}]({sub}/index.md){(' - ' + desc) if desc else ''}")
        out.append("")

    # Group concepts by type for a richer listing.
    by_type: Dict[str, List[core.Document]] = {}
    for doc in sorted(concepts, key=lambda d: d.rel_path):
        fm = doc.frontmatter or {}
        t = fm.get("type") if isinstance(fm.get("type"), str) else "Concepts"
        by_type.setdefault(t or "Concepts", []).append(doc)

    multi = len(by_type) > 1
    for t in sorted(by_type):
        if multi:
            out.append(f"## {t}")
            out.append("")
        elif concepts:
            out.append("## Concepts")
            out.append("")
        for doc in by_type[t]:
            base = os.path.basename(doc.rel_path)
            desc = _desc_for(doc)
            line = f"* [{_title_for(doc)}]({base})"
            if desc:
                line += f" - {desc}"
            out.append(line)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _all_dirs(bundle: core.Bundle) -> List[str]:
    dirs = {""}
    for doc in bundle.documents:
        if "/" in doc.rel_path:
            parts = doc.rel_path.split("/")[:-1]
            for i in range(len(parts)):
                dirs.add("/".join(parts[: i + 1]))
    return sorted(dirs)


def run(args) -> int:
    bundle = core.load_bundle(args.path)
    targets = _all_dirs(bundle) if args.recursive else [args.dir.strip("/") if args.dir else ""]

    stale = []
    for dir_rel in targets:
        version = args.okf_version if dir_rel == "" else None
        rendered = render_index(bundle, dir_rel, okf_version=version)
        index_path = os.path.join(bundle.root, dir_rel, "index.md") if dir_rel else os.path.join(bundle.root, "index.md")
        # Containment: never write/read an index outside the bundle root (rejects --dir ../x).
        if not core.is_within(index_path, bundle.root):
            print("okf index: refusing --dir that escapes the bundle root: %s" % args.dir, file=sys.stderr)
            return 2
        existing = ""
        if os.path.isfile(index_path):
            with open(index_path, "r", encoding="utf-8") as fh:
                existing = fh.read()

        if args.check:
            if existing.rstrip() != rendered.rstrip():
                stale.append(dir_rel or "(root)")
            continue
        if args.write:
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8") as fh:
                fh.write(rendered)
            print(f"wrote {os.path.relpath(index_path, bundle.root)}")
        else:
            if len(targets) > 1:
                print(f"# ---- {dir_rel or '(root)'} ----")
            print(rendered)

    if args.check:
        if stale:
            print("Stale index.md files (run with --write):", file=sys.stderr)
            for s in stale:
                print(f"  - {s}", file=sys.stderr)
            return 1
        print("All index.md files are up to date.")
        return 0
    return 0


def add_arguments(parser):
    parser.add_argument("path", help="Path to the OKF bundle root")
    parser.add_argument("--dir", default="", help="Subdirectory (relative to bundle) to index; default root")
    parser.add_argument("--recursive", action="store_true", help="Index every directory in the bundle")
    parser.add_argument("--write", action="store_true", help="Write index.md files in place")
    parser.add_argument("--check", action="store_true", help="Exit 1 if any index.md is stale (CI)")
    parser.add_argument("--okf-version", default="0.1", help="okf_version for the root index.md frontmatter")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="okf index", description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # noqa: BLE001
        print(f"okf index: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
