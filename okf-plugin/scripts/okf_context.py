"""okf_context — progressive-disclosure context selector.

The whole point of OKF is that you do NOT pour an entire bundle into a model's context.
Given a query, this returns a compact *context pack* — only the relevant concepts, as
frontmatter summaries (and optionally bodies), plus their 1-hop neighbors. With no query it
prints a lightweight outline (the map, without the contents).

This is what a skill should call instead of reading every file in a bundle.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import sys
from typing import Dict, List, Optional, Tuple

import okf_core as core

_WORD = re.compile(r"[A-Za-z0-9_]+")

FIELD_WEIGHTS = {"title": 5, "type": 3, "tags": 3, "path": 2, "description": 2, "body": 1}


def _terms(q: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(q)]


def _count(haystack: str, terms: List[str]) -> int:
    h = haystack.lower()
    return sum(h.count(t) for t in terms)


def score_concept(doc: core.Document, terms: List[str]) -> int:
    fm = doc.frontmatter or {}
    score = 0
    title = fm.get("title") if isinstance(fm.get("title"), str) else ""
    desc = fm.get("description") if isinstance(fm.get("description"), str) else ""
    ctype = fm.get("type") if isinstance(fm.get("type"), str) else ""
    tags = " ".join(str(x) for x in fm.get("tags")) if isinstance(fm.get("tags"), list) else ""
    score += FIELD_WEIGHTS["title"] * _count(title, terms)
    score += FIELD_WEIGHTS["type"] * _count(ctype, terms)
    score += FIELD_WEIGHTS["tags"] * _count(tags, terms)
    score += FIELD_WEIGHTS["path"] * _count(doc.concept_id.replace("/", " "), terms)
    score += FIELD_WEIGHTS["description"] * _count(desc, terms)
    score += FIELD_WEIGHTS["body"] * min(_count(doc.body, terms), 5)
    return score


def _resolve(doc: core.Document, link: core.Link) -> Optional[str]:
    if link.is_external or link.is_anchor_only or not link.anchorless.endswith(".md"):
        return None
    if link.is_absolute:
        return posixpath.normpath(link.anchorless.lstrip("/"))
    base = posixpath.dirname(doc.rel_path)
    return posixpath.normpath(posixpath.join(base, link.anchorless))


def neighbors(bundle: core.Bundle, selected_paths: set) -> set:
    by_path = {d.rel_path: d for d in bundle.concepts}
    out = set()
    for d in bundle.concepts:
        for link in d.links:
            tgt = _resolve(d, link)
            if tgt is None:
                continue
            if d.rel_path in selected_paths and tgt in by_path:
                out.add(tgt)
            if tgt in selected_paths and d.rel_path in by_path:
                out.add(d.rel_path)
    return out - selected_paths


def select(bundle: core.Bundle, query: str, max_concepts: int, hops: int) -> Tuple[List[core.Document], set]:
    terms = _terms(query)
    scored = [(score_concept(d, terms), d) for d in bundle.concepts]
    scored = [(s, d) for s, d in scored if s > 0]
    scored.sort(key=lambda sd: (-sd[0], sd[1].rel_path))
    primary = [d for _, d in scored[:max_concepts]]
    primary_paths = {d.rel_path for d in primary}
    related_paths = set()
    if hops >= 1 and primary_paths:
        related_paths = neighbors(bundle, primary_paths)
    by_path = {d.rel_path: d for d in bundle.concepts}
    related = [by_path[p] for p in sorted(related_paths) if p in by_path]
    return primary, set(d.rel_path for d in related), related


def _summ(doc: core.Document) -> Dict[str, object]:
    fm = doc.frontmatter or {}
    return {
        "id": doc.concept_id,
        "type": fm.get("type"),
        "title": fm.get("title") or doc.concept_id,
        "description": fm.get("description") or "",
        "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [],
        "links": sorted({_resolve(doc, l) for l in doc.links if _resolve(doc, l)}),
    }


def render_markdown(bundle, primary, related, query, mode) -> str:
    out = [f'# OKF context pack — query: "{query}"' if query else "# OKF outline"]
    out.append(f"_Selected {len(primary)} primary + {len(related)} related of "
               f"{len(bundle.concepts)} concepts from {os.path.basename(bundle.root)}._\n")

    def block(doc, tag):
        fm = doc.frontmatter or {}
        s = _summ(doc)
        lines = [f"## {s['title']} (`{s['id']}`){'  ·  related' if tag=='related' else ''}"]
        meta = f"- type: {s['type']}"
        if s["tags"]:
            meta += " | tags: " + ", ".join(str(x) for x in s["tags"])
        lines.append(meta)
        if s["description"]:
            lines.append(f"- {s['description']}")
        if s["links"]:
            lines.append("- links → " + ", ".join(s["links"]))
        if mode == "full":
            body = doc.body.strip()
            if body:
                lines.append("\n" + body)
        elif mode == "summary":
            para = _first_para(doc.body)
            if para:
                lines.append("\n> " + para)
        return "\n".join(lines)

    for doc in primary:
        out.append(block(doc, "primary"))
        out.append("")
    for doc in related:
        out.append(block(doc, "related"))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_outline(bundle) -> str:
    out = ["# OKF outline", f"_{len(bundle.concepts)} concepts in {os.path.basename(bundle.root)}._\n"]
    by_dir: Dict[str, List[core.Document]] = {}
    for d in sorted(bundle.concepts, key=lambda x: x.rel_path):
        by_dir.setdefault(posixpath.dirname(d.rel_path) or ".", []).append(d)
    for dirn in sorted(by_dir):
        out.append(f"## {dirn}")
        for d in by_dir[dirn]:
            fm = d.frontmatter or {}
            title = fm.get("title") or d.concept_id
            desc = fm.get("description") or ""
            out.append(f"* `{d.concept_id}` [{fm.get('type')}] {title}" + (f" — {desc}" if desc else ""))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _first_para(body: str) -> str:
    for block in re.split(r"\n\s*\n", body.strip()):
        b = block.strip()
        if b and not b.startswith("#") and not b.startswith("|"):
            return " ".join(b.split())
    return ""


def run(args) -> int:
    bundle = core.load_bundle(args.path)
    if not args.query:
        if args.format == "json":
            print(json.dumps({"concepts": [_summ(d) for d in bundle.concepts]}, indent=2, ensure_ascii=False))
        else:
            print(render_outline(bundle))
        return 0

    primary, _related_paths, related = select(bundle, args.query, args.max, args.hops)
    if args.format == "json":
        def with_body(d):
            s = _summ(d)
            if args.mode == "full":
                s["body"] = d.body
            return s
        payload = {
            "query": args.query,
            "primary": [with_body(d) for d in primary],
            "related": [_summ(d) for d in related],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(bundle, primary, related, args.query, args.mode))
    return 0


def add_arguments(parser):
    parser.add_argument("path", help="Path to the OKF bundle root")
    parser.add_argument("query", nargs="?", default="", help="Free-text query; omit for an outline")
    parser.add_argument("--max", type=int, default=8, help="Max primary concepts (default 8)")
    parser.add_argument("--hops", type=int, default=1, help="Neighbor expansion hops (0 to disable)")
    parser.add_argument("--mode", choices=["summary", "full", "headers"], default="summary",
                        help="summary = frontmatter + first paragraph; full = whole bodies; headers = frontmatter only")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="okf context", description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # noqa: BLE001
        print(f"okf context: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
