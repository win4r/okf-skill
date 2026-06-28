"""okf_new — scaffold a new OKF bundle or a new concept document.

Everything it emits is conformant by construction: concepts always carry a non-empty
``type``; the bundle root gets an index.md declaring ``okf_version``.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def new_bundle(path: str, title: str, okf_version: str) -> int:
    if os.path.exists(path) and os.listdir(path):
        print(f"okf new: refusing to scaffold into non-empty directory: {path}", file=sys.stderr)
        return 2
    os.makedirs(path, exist_ok=True)
    index = (
        f'---\nokf_version: "{okf_version}"\n---\n'
        f"# {title}\n\n"
        "<!-- Add sections that link to your concepts, e.g.:\n"
        "## Tables\n* [Orders](tables/orders.md) - One row per completed order.\n"
        "Run `okf index <bundle> --recursive --write` to generate these automatically. -->\n"
    )
    with open(os.path.join(path, "index.md"), "w", encoding="utf-8") as fh:
        fh.write(index)
    log = f"# Update Log\n\n## {_today()}\n* **Creation**: Initialized the {title} bundle.\n"
    with open(os.path.join(path, "log.md"), "w", encoding="utf-8") as fh:
        fh.write(log)
    print(f"Created OKF bundle at {path}/ (index.md, log.md)")
    return 0


def new_concept(bundle: str, concept_id: str, ctype: str, title: str,
                description: str, resource: str, tags, schema: bool) -> int:
    if not ctype or not ctype.strip():
        print("okf new: --type is required and must be non-empty", file=sys.stderr)
        return 2
    rel = concept_id if concept_id.endswith(".md") else concept_id + ".md"
    if os.path.isabs(rel) or os.path.relpath(os.path.normpath(os.path.join(bundle, rel)),
                                             os.path.abspath(bundle)).startswith(os.pardir):
        print("okf new: concept id must stay inside the bundle (no absolute paths or '..'): %s"
              % concept_id, file=sys.stderr)
        return 2
    dest = os.path.join(bundle, rel)
    if os.path.exists(dest):
        print(f"okf new: concept already exists: {dest}", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

    fm = [f"type: {ctype}"]
    fm.append(f"title: {title or _derive_title(concept_id)}")
    if description:
        fm.append(f"description: {description}")
    if resource:
        fm.append(f"resource: {resource}")
    if tags:
        fm.append("tags: [" + ", ".join(tags) + "]")
    fm.append(f"timestamp: {_now_iso()}")

    body = ["", "# Overview", "", description or "_Describe this concept._", ""]
    if schema:
        body += ["# Schema", "", "| Column | Type | Description |", "|--------|------|-------------|", "| | | |", ""]
    body += ["# Citations", "", "<!-- [1] [Title](https://...) -->", ""]

    content = "---\n" + "\n".join(fm) + "\n---\n" + "\n".join(body)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(content.rstrip() + "\n")
    print(f"Created concept {rel} (type: {ctype})")
    return 0


def _derive_title(concept_id: str) -> str:
    base = os.path.basename(concept_id)
    if base.endswith(".md"):
        base = base[:-3]
    return base.replace("_", " ").replace("-", " ").title()


def run(args) -> int:
    if args.kind == "bundle":
        return new_bundle(args.target, args.title or _derive_title(os.path.basename(args.target.rstrip("/"))), args.okf_version)
    if args.kind == "concept":
        if not args.bundle:
            print("okf new concept: --bundle is required", file=sys.stderr)
            return 2
        tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
        return new_concept(args.bundle, args.target, args.type, args.title,
                           args.description, args.resource, tags, args.schema)
    print(f"okf new: unknown kind {args.kind!r}", file=sys.stderr)
    return 2


def add_arguments(parser):
    parser.add_argument("kind", choices=["bundle", "concept"], help="What to create")
    parser.add_argument("target", help="Bundle path (for 'bundle') or concept id (for 'concept')")
    parser.add_argument("--bundle", help="Bundle root (required for 'concept')")
    parser.add_argument("--title", default="")
    parser.add_argument("--type", default="", help="Concept type (required for 'concept')")
    parser.add_argument("--description", default="")
    parser.add_argument("--resource", default="")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--schema", action="store_true", help="Include a # Schema table skeleton")
    parser.add_argument("--okf-version", default="0.1")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="okf new", description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # noqa: BLE001
        print(f"okf new: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
