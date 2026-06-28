"""okf_core — shared model and parsing for the OKF toolchain.

Zero third-party dependencies. Pure standard library so the tools run anywhere a
Python 3.8+ interpreter exists, with no `pip install` step.

This module deliberately contains *no policy*: it parses and models an OKF bundle.
The conformance rules (what is an error vs a warning) live in ``okf_validate``.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Filenames that OKF reserves (they are not concept documents).
RESERVED = ("index.md", "log.md")

# Repo-housekeeping files that are not OKF concepts. Skipped by default so a bundle
# committed to a git repo does not flag its README as a malformed concept.
DEFAULT_IGNORES = (
    "README.md",
    "LICENSE.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
)

# ISO 8601: a date (YYYY-MM-DD) optionally followed by a time and offset/Z.
ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?"
    r"(Z|[+-]\d{2}:?\d{2})?)?$"
)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Markdown inline link: [text](target).  Skips images (![...]).
LINK_RE = re.compile(r"(?<!\!)\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")


# --------------------------------------------------------------------------- #
# Frontmatter splitting
# --------------------------------------------------------------------------- #
@dataclass
class FrontmatterSplit:
    has_marker: bool          # did the file start with a `---` line?
    terminated: bool          # was there a closing `---`?
    raw: Optional[str]        # text between the markers (None if no frontmatter)
    body: str                 # everything after the frontmatter
    body_offset: int          # line number (1-based) where the body starts


def _is_fence(line: str) -> bool:
    """A frontmatter delimiter is exactly `---` at column 0 (trailing whitespace allowed).

    Using rstrip (not strip) means an INDENTED `---` — e.g. a markdown thematic break inside
    a `|`/`>` block scalar or a folded value, which yaml.safe_dump emits indented — is NOT
    mistaken for the closing fence. Real frontmatter fences always sit at column 0.
    """
    return line.rstrip() == "---"


def split_frontmatter(text: str) -> FrontmatterSplit:
    """Split YAML frontmatter from a Markdown document.

    A frontmatter block is a line `---` at the very start of the file, content, then a
    closing line `---` (both at column 0). Leading UTF-8 BOM is tolerated.
    """
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or not _is_fence(lines[0]):
        return FrontmatterSplit(False, False, None, text, 1)
    for i in range(1, len(lines)):
        if _is_fence(lines[i]):
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            return FrontmatterSplit(True, True, raw, body, i + 2)
    # opening marker but never closed
    return FrontmatterSplit(True, False, "\n".join(lines[1:]), "", len(lines) + 1)


# --------------------------------------------------------------------------- #
# Minimal, deterministic YAML subset parser (zero-dependency, fail-open)
# --------------------------------------------------------------------------- #
def _find_key_sep(line: str) -> int:
    """Index of the `:` that separates a mapping key from its value.

    A separator colon is one followed by a space or end-of-line, and not inside quotes.
    This keeps URL values like ``https://x`` (colon-slash, no space) intact.
    Returns -1 if the line has no key separator.
    """
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            if i + 1 == len(line) or line[i + 1] in " \t":
                return i
    return -1


def _strip_comment(s: str) -> str:
    """Remove a trailing ``#`` comment (only when ``#`` is at start or after whitespace,
    and not inside quotes)."""
    in_single = in_double = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (i == 0 or s[i - 1] in " \t"):
            return s[:i]
    return s


def _unescape_double(s: str) -> str:
    """Decode the standard YAML/JSON double-quoted escapes, preserving raw UTF-8 bytes.

    yaml.safe_dump defaults to allow_unicode=False, so non-ASCII (e.g. a Chinese `type`)
    is emitted as `\\uXXXX`; without decoding, the mini-parser would return the literal
    backslash text and diverge from PyYAML. Fails open: a malformed escape is kept verbatim.
    """
    out: List[str] = []
    i, n = 0, len(s)
    simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/", "0": "\0",
              "a": "\a", "b": "\b", "f": "\f", "v": "\v", "e": "\x1b", " ": " "}
    while i < n:
        c = s[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        nxt = s[i + 1]
        try:
            if nxt in simple:
                out.append(simple[nxt]); i += 2
            elif nxt == "x":
                out.append(chr(int(s[i + 2:i + 4], 16))); i += 4
            elif nxt == "u":
                out.append(chr(int(s[i + 2:i + 6], 16))); i += 6
            elif nxt == "U":
                out.append(chr(int(s[i + 2:i + 10], 16))); i += 10
            else:
                out.append(nxt); i += 2
        except (ValueError, OverflowError):
            out.append(c); i += 1  # fail open: keep the backslash literally
    return "".join(out)


def _scalar(token: str) -> Any:
    """Coerce a scalar token to a Python value (string, int, float, bool, None)."""
    t = token.strip()
    if not t:
        return None
    if t[0] == '"' and t[-1] == '"' and len(t) >= 2:
        return _unescape_double(t[1:-1])
    if t[0] == "'" and t[-1] == "'" and len(t) >= 2:
        return t[1:-1].replace("''", "'")  # YAML single-quote: only '' is an escape
    low = t.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    # numbers (but not version-like or date-like tokens with extra chars)
    if re.fullmatch(r"[+-]?\d+", t):
        try:
            return int(t)
        except ValueError:
            return t
    if re.fullmatch(r"[+-]?\d+\.\d+", t):
        try:
            return float(t)
        except ValueError:
            return t
    return t


def _flow_list(token: str) -> List[Any]:
    inner = token.strip()[1:-1].strip()
    if not inner:
        return []
    return [_scalar(p) for p in _split_flow(inner)]


def _split_flow(inner: str) -> List[str]:
    """Split a flow-sequence body on commas that are not inside quotes."""
    out, buf, in_single, in_double = [], [], False, False
    for ch in inner:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "," and not in_single and not in_double:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [p for p in out]


def _flow_map_pairs(token: str):
    """Parse a single flow mapping `{k: v, k2: v2}` into (key, value) pairs (best effort)."""
    inner = token.strip()[1:-1].strip()
    pairs = []
    if not inner:
        return pairs
    for part in _split_flow(inner):
        ps = part.strip()
        s = _find_key_sep(ps)
        if s > 0:
            k = ps[:s].strip()
            if (k[:1] in "\"'") and k[-1:] == k[:1] and len(k) >= 2:
                k = k[1:-1]
            pairs.append((k, _scalar(ps[s + 1:].strip())))
    return pairs


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _list_item_lines(lines: List[str], start: int) -> Tuple[Optional[List[Any]], int]:
    """If a block list (``- item`` lines, at any indent >= 0) follows, collect it.

    Returns (items_or_None, next_index). yaml.safe_dump emits list items at column 0
    under their key, so we accept both column-0 and indented ``- `` items.
    """
    items: List[Any] = []
    j = start
    n = len(lines)
    while j < n:
        la = _strip_comment(lines[j])
        if not la.strip():
            j += 1
            continue
        content = la.strip()
        if content == "-":
            items.append(None)
            j += 1
        elif content.startswith("- "):
            items.append(_scalar(content[2:].strip()))
            j += 1
        else:
            break
    return (items if items else None), j


def _gather_indented(lines: List[str], start: int) -> Tuple[List[str], int]:
    """Collect a block of more-indented (or blank) lines. Returns (stripped_lines, next)."""
    out: List[str] = []
    j = start
    n = len(lines)
    while j < n:
        ln = lines[j]
        if not ln.strip():
            out.append("")
            j += 1
            continue
        if _indent(ln) == 0:
            break
        out.append(_strip_comment(ln).strip())
        j += 1
    while out and out[-1] == "":
        out.pop()
    return out, j


def parse_yaml_mini(raw: str, _retry: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse the OKF-relevant subset of YAML. Returns (mapping, error_or_None).

    Covers the full ``yaml.safe_dump`` surface OKF producers emit: top-level
    ``key: value`` scalars, single/double-quoted strings, flow lists ``[a, b]``, block
    lists (``- item`` at column 0 or indented), ``|``/``>`` block scalars, and multi-line
    folded plain scalars (continuation lines indented under a key).

    Design invariant: **fail open**. Over-rejection violates OKF's permissive consumption
    model, so anything well-formed-but-unmodeled is accepted (best effort), and the only
    error returned is "not a mapping" — when the block has content but no top-level
    ``key:`` entry at all (a bare sequence or scalar). This makes the verdict deterministic
    and identical with or without PyYAML installed.
    """
    result: Dict[str, Any] = {}
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i, n = 0, len(lines)
    saw_content = False
    while i < n:
        rawline = lines[i]
        line = _strip_comment(rawline)
        if not line.strip():
            i += 1
            continue
        saw_content = True
        if _indent(rawline) > 0:
            # stray indented line at top level (already-consumed continuation or junk) -> skip
            i += 1
            continue
        stripped = line.strip()
        if stripped == "-" or stripped.startswith("- "):
            # top-level sequence item -> not a mapping; skip (fail open)
            i += 1
            continue
        if stripped.startswith("{") and stripped.endswith("}"):
            # whole-document flow mapping, e.g. {type: Dataset, title: Foo}
            for k, v in _flow_map_pairs(stripped):
                result[k] = v
            i += 1
            continue
        sep = _find_key_sep(stripped)
        if sep < 0:
            # bare scalar line at top level -> not a key; skip (fail open)
            i += 1
            continue
        key = stripped[:sep].strip()
        if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1]
        value_part = stripped[sep + 1:].strip()

        if value_part == "":
            items, j = _list_item_lines(lines, i + 1)
            if items is not None:
                result[key] = items
                i = j
                continue
            block, j = _gather_indented(lines, i + 1)
            if block:
                # nested map or indented multi-line plain scalar -> fold to a string (best effort)
                result[key] = " ".join(b for b in block if b)
            else:
                result[key] = None
            i = j
            continue

        if value_part[0] in "|>":
            block, j = _gather_indented(lines, i + 1)
            result[key] = "\n".join(block) if value_part[0] == "|" else " ".join(b for b in block if b)
            i = j
            continue

        if value_part.startswith("[") and value_part.endswith("]"):
            result[key] = _flow_list(value_part)
            i += 1
            continue
        if value_part.startswith("{"):
            result[key] = value_part  # flow mapping unmodeled -> keep raw (fail open)
            i += 1
            continue

        # plain scalar, possibly folded across indented continuation lines
        cont, j = _gather_indented(lines, i + 1)
        cont = [c for c in cont if c and not c.startswith("- ")]
        if cont:
            result[key] = " ".join([value_part] + cont)
            i = j
        else:
            result[key] = _scalar(value_part)
            i += 1

    if saw_content and not result:
        # Fail open on a uniformly space/tab-indented top-level mapping (valid YAML):
        # dedent by the common indent and retry once before declaring "not a mapping".
        nonblank = [ln for ln in lines if ln.strip()]
        if nonblank and not _retry:
            base = min(_indent(ln) for ln in nonblank)
            if base > 0:
                dedented = "\n".join(ln[base:] if len(ln) >= base else ln for ln in lines)
                return parse_yaml_mini(dedented, _retry=True)
        return None, "frontmatter is not a mapping"
    return result, None


def parse_frontmatter(raw: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse a frontmatter block deterministically with the zero-dependency mini-parser.

    Returns (data, error_message). The mini-parser is the single canonical verdict — no
    PyYAML at runtime — so conformance is reproducible on any stdlib-only interpreter. A
    CI test asserts the mini-parser's accept/reject verdict matches PyYAML on real bundles.
    """
    data, err = parse_yaml_mini(raw)
    if err:
        return None, err
    return data, None


# --------------------------------------------------------------------------- #
# Link extraction
# --------------------------------------------------------------------------- #
@dataclass
class Link:
    text: str
    target: str
    line: int

    @property
    def anchorless(self) -> str:
        return self.target.split("#", 1)[0]

    @property
    def is_external(self) -> bool:
        return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", self.target)) or self.target.startswith("//")

    @property
    def is_anchor_only(self) -> bool:
        return self.target.startswith("#")

    @property
    def is_absolute(self) -> bool:
        return self.target.startswith("/")


def extract_links(body: str) -> List[Link]:
    links: List[Link] = []
    for lineno, line in enumerate(body.split("\n"), start=1):
        for m in LINK_RE.finditer(line):
            links.append(Link(m.group("text"), m.group("target"), lineno))
    return links


# --------------------------------------------------------------------------- #
# Document + bundle model
# --------------------------------------------------------------------------- #
@dataclass
class Document:
    path: str                       # absolute path on disk
    rel_path: str                   # path relative to bundle root, posix-style
    kind: str                       # "concept" | "index" | "log" | "ignored"
    is_root_index: bool = False
    decode_error: bool = False
    text: str = ""
    fm: FrontmatterSplit = field(default_factory=lambda: FrontmatterSplit(False, False, None, "", 1))
    frontmatter: Optional[Dict[str, Any]] = None
    fm_error: Optional[str] = None
    body: str = ""
    links: List[Link] = field(default_factory=list)

    @property
    def concept_id(self) -> str:
        return self.rel_path[:-3] if self.rel_path.endswith(".md") else self.rel_path


@dataclass
class Bundle:
    root: str
    documents: List[Document] = field(default_factory=list)

    @property
    def concepts(self) -> List[Document]:
        return [d for d in self.documents if d.kind == "concept"]

    @property
    def rel_paths(self) -> set:
        return {d.rel_path for d in self.documents}


def classify(filename: str, rel_path: str, default_ignores: bool) -> str:
    base = os.path.basename(filename)
    if base == "index.md":
        return "index"
    if base == "log.md":
        return "log"
    if default_ignores and base in DEFAULT_IGNORES:
        return "ignored"
    return "concept"


def load_document(path: str, rel_path: str, root: str, default_ignores: bool = True) -> Document:
    rel_posix = rel_path.replace(os.sep, "/")
    kind = classify(path, rel_posix, default_ignores)
    is_root_index = kind == "index" and "/" not in rel_posix
    doc = Document(path=path, rel_path=rel_posix, kind=kind, is_root_index=is_root_index)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        doc.text = data.decode("utf-8")
    except UnicodeDecodeError:
        doc.decode_error = True
        return doc
    doc.fm = split_frontmatter(doc.text)
    doc.body = doc.fm.body if doc.fm.has_marker else doc.text
    if doc.fm.has_marker and doc.fm.terminated:
        doc.frontmatter, doc.fm_error = parse_frontmatter(doc.fm.raw or "")
    doc.links = extract_links(doc.body)
    return doc


def is_within(path: str, root: str) -> bool:
    """True iff `path` (after resolving symlinks) is inside `root`. Containment-safe."""
    real = os.path.realpath(path)
    root_real = os.path.realpath(root)
    return real == root_real or real.startswith(root_real + os.sep)


def load_bundle(root: str, default_ignores: bool = True, extra_ignores: Optional[List[str]] = None) -> Bundle:
    root = os.path.abspath(root)
    bundle = Bundle(root=root)
    extra = extra_ignores or []
    # followlinks=False: do not descend into symlinked directories.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            full = os.path.join(dirpath, fn)
            # Never read a symlinked file whose target escapes the bundle root (exfil guard).
            if os.path.islink(full) and not is_within(full, root):
                continue
            rel = os.path.relpath(full, root)
            rel_posix = rel.replace(os.sep, "/")
            if any(_glob_match(rel_posix, g) for g in extra):
                continue
            bundle.documents.append(load_document(full, rel, root, default_ignores))
    return bundle


def _glob_match(rel_path: str, pattern: str) -> bool:
    import fnmatch
    base = rel_path.rsplit("/", 1)[-1]
    return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(base, pattern)


def is_iso8601(value: Any) -> bool:
    return isinstance(value, str) and bool(ISO8601_RE.match(value.strip()))


def is_iso_date(value: Any) -> bool:
    return isinstance(value, str) and bool(ISO_DATE_RE.match(value.strip()))
