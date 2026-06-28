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

# --- YAML 1.1 implicit-scalar resolvers (mirror PyYAML's core schema) ---------
# Used so the mini-parser coerces ONLY what PyYAML coerces (no over-rejection), and the
# producer emitter (emit_scalar) quotes anything PyYAML would resolve to a non-string.
_YAML_BOOL_RE = re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$")
_YAML_NULL_RE = re.compile(r"^(?:~|null|Null|NULL)$")
# int: binary, octal (leading 0 OR 0o), decimal (no leading-zero ambiguity), hex, sexagesimal
_YAML_INT_RE = re.compile(
    r"^(?:[-+]?0b[0-1_]+|[-+]?0o?[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)"
    r"|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$"
)
_YAML_FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.[0-9][0-9_]*(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)
# decimal-only int (the form that actually appears bare in yaml.safe_dump output)
_DECIMAL_INT_RE = re.compile(r"^[-+]?(?:0|[1-9][0-9_]*)$")
_DECIMAL_FLOAT_RE = re.compile(r"^[-+]?[0-9][0-9_]*\.[0-9_]+$")


def _yaml_implicit_nonstring(s: str) -> bool:
    """True if PyYAML's YAML 1.1 resolver would read bare ``s`` as a non-string
    (bool/null/int/float/timestamp). Used to decide producer quoting."""
    if not isinstance(s, str) or s == "":
        return s == ""
    return bool(
        _YAML_BOOL_RE.match(s) or _YAML_NULL_RE.match(s)
        or _YAML_INT_RE.match(s) or _YAML_FLOAT_RE.match(s)
        or ISO8601_RE.match(s)
    )


# Markdown inline link: [text](target).  Skips images (![...]).
LINK_RE = re.compile(r"(?<!\!)\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
# Fenced code block delimiter (``` or ~~~), used to skip code when extracting links.
FENCE_RE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN_RE = re.compile(r"(`+)(?:.*?)\1")


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
            elif nxt in "uU":
                width = 4 if nxt == "u" else 8
                cp = int(s[i + 2:i + 2 + width], 16)
                consumed = 2 + width
                # Combine a UTF-16 surrogate PAIR (\uD800-\uDBFF followed by \uDC00-\uDFFF).
                if 0xD800 <= cp <= 0xDBFF and s[i + consumed:i + consumed + 2] == "\\u":
                    lo = int(s[i + consumed + 2:i + consumed + 6], 16)
                    if 0xDC00 <= lo <= 0xDFFF:
                        out.append(chr(0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)))
                        i += consumed + 6
                        continue
                if 0xD800 <= cp <= 0xDFFF:
                    # A lone surrogate is not UTF-8-encodable -> fail open, keep the escape literal
                    # so downstream serializers (graph/index/context) never crash.
                    out.append(s[i:i + consumed]); i += consumed
                else:
                    out.append(chr(cp)); i += consumed
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
    # numbers — match PyYAML's DECIMAL resolver only (the form that appears bare in
    # yaml.safe_dump output). A leading-zero token like 09 is NOT a decimal int in YAML 1.1,
    # so it must stay a STRING (coercing it to int 9 was a cardinal-rule over-rejection).
    if _DECIMAL_INT_RE.match(t):
        try:
            return int(t.replace("_", ""))
        except ValueError:
            return t
    if _DECIMAL_FLOAT_RE.match(t):
        try:
            return float(t.replace("_", ""))
        except ValueError:
            return t
    return t


def _flow_list(token: str) -> List[Any]:
    inner = token.strip()[1:-1].strip()
    if not inner:
        return []
    return [_scalar(p) for p in _split_flow(inner)]


def _split_flow(inner: str) -> List[str]:
    """Split a flow body on commas at depth 0 that are not inside quotes (so commas inside
    a nested ``{...}`` / ``[...]`` are not treated as separators)."""
    out, buf, in_single, in_double, depth = [], [], False, False, 0
    for ch in inner:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth = max(0, depth - 1)
        if ch == "," and not in_single and not in_double and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [p for p in out]


def _brace_balance(s: str) -> int:
    """Net `{` minus `}` count outside quotes (used to gather a multi-line flow mapping)."""
    depth, in_single, in_double = 0, False, False
    for ch in s:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
    return depth


_FLOW_MAX_DEPTH = 64  # bound mutual recursion so a pathological nested flow map can't blow the stack


def _flow_value(val: str, depth: int = 0) -> Any:
    """Parse a flow value: a nested list, a nested map, or a scalar."""
    val = val.strip()
    if depth >= _FLOW_MAX_DEPTH:
        return val  # too deeply nested -> keep raw (fail open)
    if val.startswith("[") and val.endswith("]"):
        return _flow_list(val)
    if val.startswith("{") and val.endswith("}"):
        return dict(_flow_map_pairs(val, depth + 1))
    return _scalar(val)


def _flow_map_pairs(token: str, depth: int = 0):
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
            pairs.append((k, _flow_value(ps[s + 1:].strip(), depth)))
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
    """Collect a block of more-indented (or blank) lines. Returns (stripped_lines, next).

    Comments are NOT stripped here: these continuation lines are the *content* of a block
    scalar (|/>) or a multi-line quoted/folded value, where a leading '#' is real text, so
    stripping it would corrupt the value (and could lose a closing quote -> over-rejection).
    """
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
        out.append(ln.strip())
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
    saw_mapping = False  # recognized mapping syntax (a key, or a flow map even if empty)
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
        if stripped.startswith("{"):
            # whole-document flow mapping (possibly split across lines), e.g.
            # {type: Dataset, title: Foo}  or  {type: Table,\n title: Foo}
            saw_mapping = True
            buf = stripped
            j = i
            while _brace_balance(buf) > 0 and j + 1 < n:
                j += 1
                buf += " " + lines[j].strip()  # do not strip '#': may be inside a quoted value
            for k, v in _flow_map_pairs(buf):
                result[k] = v
            i = j + 1
            continue
        sep = _find_key_sep(stripped)
        if sep < 0:
            # bare scalar line at top level -> not a key; skip (fail open)
            i += 1
            continue
        saw_mapping = True
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
            if block and _find_key_sep(block[0]) >= 0:
                # an indented block whose first line has a key separator is a nested MAPPING
                # (valid yaml.safe_dump output) -> represent as a dict so a mapping-valued
                # `type` correctly trips E005, matching PyYAML.
                nested, _err = parse_yaml_mini("\n".join(block))
                result[key] = nested if isinstance(nested, dict) else {}
            elif block:
                # indented multi-line plain scalar -> fold to a string (best effort)
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
        if value_part.startswith("{") and value_part.endswith("}"):
            # value-position flow mapping (type: {a: b}) -> dict, so a mapping `type` trips E005
            result[key] = dict(_flow_map_pairs(value_part))
            i += 1
            continue
        if value_part.startswith("{"):
            result[key] = value_part  # unterminated/odd flow mapping -> keep raw (fail open)
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

    if saw_content and not result and not saw_mapping:
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
    try:
        data, err = parse_yaml_mini(raw)
    except RecursionError:
        # pathological deeply-nested input -> fail open for THIS file (don't abort the run)
        return None, "frontmatter too deeply nested"
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


def _strip_code_spans(line: str) -> str:
    """Blank out inline code spans (`...`) so links inside them are not extracted."""
    return CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)


def extract_links(body: str) -> List[Link]:
    """Extract Markdown links, skipping fenced code blocks and inline code spans (a link
    shown as a code EXAMPLE is not a real cross-link, so it must not produce a broken-link
    warning)."""
    links: List[Link] = []
    in_fence = False
    for lineno, line in enumerate(body.split("\n"), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in LINK_RE.finditer(_strip_code_spans(line)):
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


# --------------------------------------------------------------------------- #
# Frontmatter serialization (shared by okf_new and okf_migrate so producer output is
# round-trip-safe: a value never re-parses to a different value/type than intended, and is
# always parseable by a standard YAML reader).
# --------------------------------------------------------------------------- #
def _has_control(s: str) -> bool:
    return any(ord(c) < 0x20 or ord(c) == 0x7f for c in s)


def _quote_double(s: str) -> str:
    """Double-quote a scalar, escaping backslash, quote, and C0/DEL control chars so the
    result is parseable by a standard YAML reader (which rejects raw control bytes)."""
    out = []
    for ch in s:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif o < 0x20 or o == 0x7f:
            out.append("\\x%02x" % o)
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def emit_scalar(value: Any, in_flow: bool = False) -> str:
    """Serialize a scalar for frontmatter, quoting whenever bare YAML would be re-typed,
    mis-parsed, or rejected by a standard YAML reader. Over-quoting is always safe."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if not isinstance(value, str):
        return str(value)
    needs = (
        value == ""
        or value.strip() != value
        or value[:1] in "[]{}!&*#?|>@`\"'%,:-"   # leading YAML indicator (incl ] } :)
        or value[-1:] == ":"
        or ": " in value or " #" in value
        or _has_control(value)                    # tab/CR/etc. -> bare YAML is unparseable
        or _yaml_implicit_nonstring(value)        # bool/null/int/float/timestamp -> re-typed
        or (in_flow and any(c in value for c in ",[]{}"))  # flow-list/map separators
    )
    return _quote_double(value) if needs else value


def emit_fm(key: str, value: Any) -> List[str]:
    """Emit one frontmatter key as one or more lines (block scalar for multi-line strings)."""
    if isinstance(value, list):
        return ["%s: [%s]" % (key, ", ".join(emit_scalar(x, in_flow=True) for x in value))]
    if isinstance(value, str) and "\n" in value:
        out = ["%s: |" % key]
        for ln in value.split("\n"):
            out.append(("  " + ln) if ln else "")
        return out
    return ["%s: %s" % (key, emit_scalar(value))]
