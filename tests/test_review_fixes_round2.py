"""Regression tests for the 11 findings confirmed by the SECOND adversarial review round
(mostly regressions / incomplete fixes introduced by the round-1 fixes)."""
import os
import types

import okf_core as core
import okf_validate as v
import okf_context
import okf_graph
import okf_index
import okf_new
import okf_migrate
from conftest import ROOT_INDEX, CONCEPT_OK, codes


def _val(root, **kw):
    return v.validate_bundle(core.load_bundle(root), **kw)


# R2-1 — lone surrogate escape must not crash context/index/graph (was a UnicodeEncodeError)
def test_r2_1_lone_surrogate_no_downstream_crash(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX,
                        "a.md": '---\ntype: Concept\ntitle: "\\uDE00"\n---\nalpha body\n'})
    assert _val(root).conformant
    # all three downstream tools must run without UnicodeEncodeError
    assert okf_context.run(types.SimpleNamespace(path=root, query="alpha", max=8, hops=1,
                                                 mode="summary", format="json")) == 0
    assert okf_index.run(types.SimpleNamespace(path=root, dir="", recursive=True, write=True,
                                               check=False, okf_version="0.1")) == 0
    assert okf_graph.run(types.SimpleNamespace(path=root, format="json", output=None, title="")) == 0


def test_r2_1_surrogate_pair_combines():
    d, _ = core.parse_frontmatter('type: "\\uD83D\\uDE00"')
    assert d["type"] == "😀" and d["type"].encode("utf-8")  # encodable, real emoji


# R2-2 — multi-line top-level flow mapping is conformant (not E004)
def test_r2_2_multiline_flow_mapping_conformant(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\n{type: Table,\n title: Foo}\n---\nbody\n"})
    res = _val(root)
    assert res.conformant and "E004" not in codes(res)


# R2-3 — nested flow structures keep correct values (no spurious keys / W013)
def test_r2_3_nested_flow_no_spurious_keys():
    d, _ = core.parse_frontmatter("{type: T, meta: {a: 1, b: 2}, tags: [x, y]}")
    assert d["type"] == "T" and d["tags"] == ["x", "y"] and "b" not in d


# R2-4 — E008 accepts a valid ISO date glued to punctuation (the common changelog style)
def test_r2_4_e008_accepts_punctuation_glued_date(make_bundle):
    for sep in (":", ",", ".", ";"):
        root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
                            "log.md": f"# Log\n\n## 2026-05-01{sep} Release notes\n* x\n"})
        res = _val(root)
        assert res.conformant, (sep, codes(res))
        assert "E008" not in codes(res)
    # genuinely malformed date still errors
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
                        "log.md": "# Log\n\n## 2026-5-1: x\n"})
    assert "E008" in codes(_val(root))


# R2-5 / R2-6 — producers must not emit numeric-looking unquoted types (self-de-conform)
def test_r2_6_migrate_keeps_numeric_string_type_conformant(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text('---\ntype: "5"\ntitle: N\ndescription: x.\n'
                             'timestamp: 2026-05-28T14:30:00Z\n---\n# N\nbody\n')
    assert _val(str(src)).conformant  # source is conformant (type is the string "5")
    out = str(tmp_path / "out")
    okf_migrate.run(types.SimpleNamespace(path=str(src), out=out, write=False,
                                          default_type="Note", regenerate_index=False))
    assert 'type: "5"' in (tmp_path / "out" / "a.md").read_text()  # quoted on output
    assert _val(out).conformant                                    # ...so it stays conformant


def test_r2_6_new_concept_numeric_type_conformant(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    okf_new.new_concept(bundle, "x", "5", "", "", "", [], False)
    assert _val(bundle).conformant  # type:"5" emitted quoted -> still a string


# R2-7 — on/off strings are quoted so mini and PyYAML agree
def test_r2_7_on_off_quoted():
    assert core.emit_scalar("on") == '"on"' and core.emit_scalar("off") == '"off"'
    line = core.emit_fm("type", "on")[0]
    assert core.parse_frontmatter(line)[0]["type"] == "on"  # stays a string


# R2-8 — a tag containing a comma is not split into multiple tags
def test_r2_8_comma_in_tag_preserved():
    line = core.emit_fm("tags", ["machine, learning", "ai"])[0]
    back, _ = core.parse_frontmatter(line)
    assert back["tags"] == ["machine, learning", "ai"]


# R2-9 — okf_new containment accepts an in-bundle '..foo' dir but rejects real escapes
def test_r2_9_new_containment_realpath(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    assert okf_new.new_concept(bundle, "..notes/real", "Note", "", "", "", [], False) == 0  # inside
    assert okf_new.new_concept(bundle, "../../evil", "Note", "", "", "", [], False) == 2    # escapes
    assert not os.path.exists(str(tmp_path / "evil.md"))


# R2-10 — a wikilink in a backslash-escaped backtick run IS converted (it is literal text)
def test_r2_10_escaped_backtick_wikilink_converted():
    rep = okf_migrate.FileReport(rel="t.md")
    out = okf_migrate.convert_wikilinks(r"\`[[Page]]\` and `[[Page]]`", {"page": "p.md"}, rep)
    assert r"\`[Page](/p.md)\`" in out      # escaped-backtick text converted
    assert "`[[Page]]`" in out              # genuine code span untouched


# R2-11 — migrate --out must not dereference a symlinked reserved file escaping the bundle
def test_r2_11_migrate_no_symlink_exfil(tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("SUPER SECRET\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "note.md").write_text("# Note\n\nbody\n")
    os.symlink(str(secret), str(src / "index.md"))  # reserved file symlink escaping the bundle
    out = str(tmp_path / "out")
    okf_migrate.run(types.SimpleNamespace(path=str(src), out=out, write=False,
                                          default_type="Note", regenerate_index=False))
    out_index = tmp_path / "out" / "index.md"
    # the escaping symlink was skipped; a fresh stub was generated instead (no secret content)
    assert not out_index.exists() or "SUPER SECRET" not in out_index.read_text()
