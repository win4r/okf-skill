"""Regression tests for the findings confirmed by the THIRD adversarial review round.
Numbers reference the confirmed-findings list (R3-N)."""
import os
import types

import pytest

import okf_core as core
import okf_validate as v
import okf_context
import okf_graph
import okf_index
from conftest import ROOT_INDEX, CONCEPT_OK, codes

yaml = pytest.importorskip("yaml")


def _val(root, **kw):
    return v.validate_bundle(core.load_bundle(root), **kw)


# R3-1 — _scalar must not coerce leading-zero ints; `type: 09` stays a conformant string
def test_r3_1_leading_zero_int_type_conformant(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntype: 09\ntitle: X\n---\nbody\n"})
    res = _val(root)
    assert res.conformant and "E005" not in codes(res)
    assert yaml.safe_load("type: 09")["type"] == "09"  # PyYAML agrees it's a string


# R3-2 — producer output is always PyYAML-parseable (control chars / leading ]/} / implicit)
@pytest.mark.parametrize("val", ["a\tb", "]note", "}note", "c:", "0x1f", "2026-01-01",
                                 "12:30:00", ".inf", "on", "1_000", "09"])
def test_r3_2_emit_is_pyyaml_parseable_and_roundtrips(val):
    line = core.emit_fm("type", val)[0]
    assert core.parse_frontmatter(line)[0]["type"] == val      # mini round-trips
    assert yaml.safe_load(line)["type"] == val                 # PyYAML round-trips (string)


# R3-9 — a '## date' inside a code fence in log.md is not a heading (no false E008)
def test_r3_9_log_fence_no_false_e008(make_bundle):
    log = "# Log\n\n```\n## 05/22/2026\n* x\n```\n\n## 2026-05-22\n* real\n"
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK, "log.md": log})
    res = _val(root)
    assert res.conformant and "E008" not in codes(res)


# R3-4 — a '#'-leading line inside a |-block scalar is preserved (not eaten as a comment)
def test_r3_4_hash_in_block_scalar_preserved():
    d, _ = core.parse_frontmatter("type: Note\nbody: |\n  intro\n  # Heading\n  out")
    assert d["body"] == "intro\n# Heading\nout"


# R3-5 — deep nested flow must NOT crash the run (depth cap / fail open)
def test_r3_5_deep_nesting_no_crash(make_bundle):
    deep = "x"
    for _ in range(900):
        deep = "{a: " + deep + "}"
    core.parse_frontmatter(deep)   # must NOT raise RecursionError (depth cap truncates)
    # a bundle containing the pathological file still validates its sibling (no whole-run abort)
    root = make_bundle({"index.md": ROOT_INDEX, "evil.md": "---\n" + deep + "\n---\nb\n", "good.md": CONCEPT_OK})
    res = _val(root)                                # completes without raising
    assert not res.conformant                       # evil.md has no `type` (E004/E003)
    assert any(d.rel_path == "good.md" for d in core.load_bundle(root).concepts)


# R3-12/15 — a mapping-valued `type` (block OR flow) trips E005 (matches PyYAML)
def test_r3_12_block_mapping_type_e005(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntype:\n  name: T\n  schema: pub\ntitle: A\n---\nb\n"})
    assert "E005" in codes(_val(root))


def test_r3_15_flow_mapping_type_e005(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntype: {a: b}\ntitle: A\n---\nb\n"})
    assert "E005" in codes(_val(root))
    # but an indented multi-line plain scalar (no key sep) stays a string -> conformant
    root2 = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntype:\n  multi line\n  plain scalar\n---\nb\n"})
    assert _val(root2).conformant


# R3-7 — a malformed .okf.yml must not crash validate (fail open to defaults)
def test_r3_7_malformed_okf_yml_no_crash(make_bundle):
    for bad in ("description_max_chars: lots\n", "stale_after_days: 30d\n", "concrete_types: 5\n"):
        root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK, ".okf.yml": bad})
        args = types.SimpleNamespace(path=root, format="json", profile="conformance", strict=False,
                                     pedantic=False, no_links=False, no_color=True,
                                     no_default_ignores=False, ignore=[])
        assert v.run(args) == 0, bad  # conformant, no exit-2 crash


# R3-20 — Q005 stale-timestamp is now implemented
def test_r3_20_q005_stale_timestamp(make_bundle):
    files = {
        "index.md": ROOT_INDEX,
        ".okf.yml": "profile: strict\nstale_after_days: 1\n",
        "old.md": "---\ntype: T\ntitle: Old\ndescription: d\ntimestamp: 2000-01-01T00:00:00Z\n---\nbody\n",
    }
    root = make_bundle(files)
    cfg = v.ProjectConfig.load(root)
    res = v.validate_bundle(core.load_bundle(root), profile="strict", config=cfg)
    assert "Q005" in codes(res) and res.conformant  # quality lint, never breaks conformance


# R3-13 — links inside code fences/spans don't produce false W005
def test_r3_13_links_in_code_not_flagged(make_bundle):
    body = CONCEPT_OK + "\n```\n[ghost](does_not_exist.md)\n```\ninline `[also](gone.md)` here\n"
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": body})
    res = _val(root)
    assert "W005" not in codes(res)


# R3-21 — CJK query tokenizes and matches
def test_r3_21_cjk_query(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "u.md": "---\ntype: T\ntitle: 用户数据\ndescription: d\n---\nbody\n"})
    primary, _r, _rel = okf_context.select(core.load_bundle(root), "用户", max_concepts=8, hops=1)
    assert [d.rel_path for d in primary] == ["u.md"]


# R3-22 — --hops 2 reaches a 2-hop neighbor
def test_r3_22_multi_hop(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "a.md": "---\ntype: T\ntitle: Alpha\n---\n[b](/b.md)\n",
        "b.md": "---\ntype: T\ntitle: Beta\n---\n[c](/c.md)\n",
        "c.md": "---\ntype: T\ntitle: Gamma\n---\nleaf\n",
    })
    b = core.load_bundle(root)
    _p, _r, rel1 = okf_context.select(b, "alpha", max_concepts=1, hops=1)
    _p, _r, rel2 = okf_context.select(b, "alpha", max_concepts=1, hops=2)
    assert "c.md" not in {d.rel_path for d in rel1}   # 1 hop reaches only b
    assert "c.md" in {d.rel_path for d in rel2}        # 2 hops reaches c


# R3-23 — index/context/graph fail fast (exit 2) on a non-existent path (no dir creation)
def test_r3_23_isdir_guard(tmp_path):
    ghost = str(tmp_path / "ghost" / "typo")
    assert okf_index.main([ghost, "--write"]) == 2
    assert not os.path.exists(str(tmp_path / "ghost"))  # nothing materialized
    assert okf_context.main([ghost, "q"]) == 2
    assert okf_graph.main([ghost]) == 2
