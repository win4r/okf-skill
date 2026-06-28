"""Regression tests for the 15 findings confirmed by the adversarial review.

Each test reproduces a reviewer's exact scenario and asserts the fix holds. Numbers map to
the confirmed-findings list in the review.
"""
import os
import types

import pytest

import okf_core as core
import okf_validate as v
import okf_context
import okf_index
import okf_new
import okf_migrate
from conftest import ROOT_INDEX, CONCEPT_OK, codes


def _val(root, **kw):
    return v.validate_bundle(core.load_bundle(root), **kw)


# 1 — E008 must NOT over-reject a valid ISO date carrying a title, nor numeric prose
def test_fix1_e008_accepts_titled_iso_date_and_ignores_numeric_prose(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
        "log.md": "# Log\n\n## 2026-05-01 Sprint planning\n* x\n\n## 3-2-1 launch checklist\n* y\n",
    })
    res = _val(root)
    assert res.conformant, codes(res)          # both headings tolerated
    assert "E008" not in codes(res)


def test_fix1_e008_still_catches_real_malformed_date(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
                        "log.md": "# Log\n\n## 05/22/2026\n* x\n"})
    assert "E008" in codes(_val(root)) and not _val(root).conformant


# 2 / 6 — an indented '---' inside a block scalar must not truncate frontmatter (drops type)
def test_fix2_indented_rule_in_block_scalar_keeps_type(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "a.md": "---\ndescription: |\n  intro\n  ---\n  outro\ntype: Table\n---\n# A\nbody\n",
    })
    res = _val(root)
    assert res.conformant, codes(res)
    doc = [d for d in core.load_bundle(root).concepts if d.rel_path == "a.md"][0]
    assert doc.frontmatter["type"] == "Table"


# 3 — uniformly-indented top-level mapping is valid YAML and must parse
def test_fix3_indented_mapping_parses():
    d, e = core.parse_frontmatter("  type: Table\n  title: A")
    assert e is None and d == {"type": "Table", "title": "A"}


# 7 — top-level flow mapping must extract type
def test_fix7_top_level_flow_mapping(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\n{type: Table, title: Foo}\n---\nbody\n"})
    res = _val(root)
    assert res.conformant and "E004" not in codes(res)


# 4 — E005 must catch non-string scalar type
def test_fix4_e005_non_string_type(make_bundle):
    for val in ("5", "true", "1.5"):
        root = make_bundle({"index.md": ROOT_INDEX, "a.md": f"---\ntype: {val}\n---\nbody\n"})
        assert "E005" in codes(_val(root)), val
    # a quoted numeric type is a valid string and must NOT be flagged
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": '---\ntype: "5"\n---\nbody\n'})
    assert "E005" not in codes(_val(root))


# 5 — a non-existent bundle path is a tool error (exit 2), not vacuously conformant
def test_fix5_missing_path_exits_2():
    assert v.main(["/no/such/okf/path/xyz", "--format", "json"]) == 2


# 8 — non-ASCII \uXXXX escapes (default safe_dump output) decode to real characters
def test_fix8_non_ascii_escape_decoded():
    d, e = core.parse_frontmatter('type: "\\u6570\\u636e\\u96c6"')
    assert e is None and d["type"] == "数据集"


# 9 — a symlinked .md whose target escapes the bundle is NOT read (no exfil).
# The bundle is a SUBDIR so the secret genuinely lives outside the bundle root.
def test_fix9_symlink_escape_not_read(tmp_path):
    secret = tmp_path / "secret.txt"  # outside the bundle
    secret.write_text("---\ntype: leak\ntitle: SECRET\n---\nprivate body\n")
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "index.md").write_text(ROOT_INDEX)
    (root / "a.md").write_text(CONCEPT_OK)
    os.symlink(str(secret), str(root / "leak.md"))
    bundle = core.load_bundle(str(root))
    assert "leak.md" not in {d.rel_path for d in bundle.documents}  # never loaded


def test_fix9_link_to_symlink_outside_root_is_w015_not_stat(tmp_path):
    outside = tmp_path / "outside.md"  # outside the bundle
    outside.write_text("x")
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "index.md").write_text(ROOT_INDEX)
    (root / "a.md").write_text(CONCEPT_OK + "\n[x](ext.md)\n")
    os.symlink(str(outside), str(root / "ext.md"))
    res = _val(str(root))
    assert "W015" in codes(res) and res.conformant  # escapes -> warning, never an error


# 10 — an in-bundle directory literally named '..foo' is inside the root (no false W015)
def test_fix10_dotdot_named_dir_not_flagged(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "..notes/real.md": CONCEPT_OK,
        "a.md": CONCEPT_OK + "\n[inside](/..notes/real.md)\n",
    })
    res = _val(root)
    assert "W015" not in codes(res)  # the target is physically inside the root


# 11 — index/new must refuse to write outside the bundle root
def test_fix11_index_refuses_dir_escape(make_bundle, tmp_path, capsys):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK})
    args = types.SimpleNamespace(path=root, dir="../ESCAPED", recursive=False, write=True,
                                 check=False, okf_version="0.1")
    assert okf_index.run(args) == 2
    assert not os.path.exists(os.path.join(os.path.dirname(root), "ESCAPED"))


def test_fix11_new_concept_refuses_escape(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    assert okf_new.new_concept(bundle, "../../evil", "Note", "", "", "", [], False) == 2
    assert not os.path.exists(str(tmp_path / "evil.md"))


# 12 — okf context must not crash on numeric tags
def test_fix12_context_numeric_tags(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX,
                        "a.md": "---\ntype: note\ntitle: A\ntags: [2024, 2025]\n---\nalpha body\n"})
    assert v.validate_bundle(core.load_bundle(root)).conformant  # conformant input
    args = types.SimpleNamespace(path=root, query="alpha", max=8, hops=1, mode="summary", format="markdown")
    assert okf_context.run(args) == 0  # no TypeError crash


# 13 — migrate --out preserves existing index.md / log.md
def test_fix13_migrate_preserves_reserved(tmp_path):
    src = tmp_path / "src"
    (src / "topics").mkdir(parents=True)
    (src / "index.md").write_text("# Root\n\nIMPORTANT_ROOT\n")
    (src / "topics" / "index.md").write_text("# Sub\n\nSUBINDEX_CONTENT\n")
    (src / "topics" / "t.md").write_text("# T\n\nnote\n")
    (src / "log.md").write_text("# Update Log\n\n## 2025-01-01\n* HANDWRITTEN\n")
    out = str(tmp_path / "out")
    okf_migrate.run(types.SimpleNamespace(path=str(src), out=out, write=False,
                                          default_type="Note", regenerate_index=False))
    assert "IMPORTANT_ROOT" in (tmp_path / "out" / "index.md").read_text()
    assert "SUBINDEX_CONTENT" in (tmp_path / "out" / "topics" / "index.md").read_text()
    assert "HANDWRITTEN" in (tmp_path / "out" / "log.md").read_text()


# 14 — wikilinks inside inline code spans are not rewritten
def test_fix14_wikilink_in_inline_code_preserved():
    rep = okf_migrate.FileReport(rel="t.md")
    out = okf_migrate.convert_wikilinks("Use `[[Page Name]]` but link [[Page Name]].",
                                        {"page-name": "p.md"}, rep)
    assert "`[[Page Name]]`" in out          # code span untouched
    assert "[Page Name](/p.md)" in out       # the real one converted


# 15 — re-emitting a '|' block scalar round-trips (no silent truncation)
def test_fix15_migrate_roundtrip_block_scalar(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "n.md").write_text(
        "---\ntype: Reference\ntitle: N\ndescription: |\n  First line.\n  Second crucial line.\n---\n# N\nbody\n")
    out = str(tmp_path / "out")
    okf_migrate.run(types.SimpleNamespace(path=str(src), out=out, write=False,
                                          default_type="Note", regenerate_index=False))
    text = (tmp_path / "out" / "n.md").read_text()
    split = core.split_frontmatter(text)
    d, _ = core.parse_frontmatter(split.raw)
    assert "Second crucial line." in d["description"]  # not truncated on re-parse
