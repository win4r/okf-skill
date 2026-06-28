"""Conformance + lint behavior of okf_validate. Each test isolates one code."""
import okf_core as core
import okf_validate as v
from conftest import CONCEPT_OK, ROOT_INDEX, codes


def _validate(root, **kw):
    bundle = core.load_bundle(root)
    return v.validate_bundle(bundle, **kw)


# --------------------------------------------------------------------------- #
# Core parsing
# --------------------------------------------------------------------------- #
def test_mini_yaml_url_not_truncated():
    d, e = core.parse_frontmatter("type: T\nresource: https://x.com/a?b=1#c")
    assert e is None and d["resource"] == "https://x.com/a?b=1#c"


def test_mini_yaml_flow_and_block_lists():
    d, _ = core.parse_frontmatter("tags: [a, b, c]")
    assert d["tags"] == ["a", "b", "c"]
    d, _ = core.parse_frontmatter("tags:\n  - a\n  - b\n")
    assert d["tags"] == ["a", "b"]


def test_mini_yaml_types():
    d, _ = core.parse_frontmatter("a: true\nb: false\nc: null\nd: 42\ne: 1.5\nf: hi")
    assert d == {"a": True, "b": False, "c": None, "d": 42, "e": 1.5, "f": "hi"}


def test_frontmatter_split_variants():
    assert not core.split_frontmatter("no fm\nbody").has_marker
    s = core.split_frontmatter("---\ntype: X\nbody-no-close")
    assert s.has_marker and not s.terminated
    s = core.split_frontmatter("---\ntype: X\n---\n# Body")
    assert s.has_marker and s.terminated and s.body.strip() == "# Body"


def test_link_classification():
    links = core.extract_links("[a](/x.md) [b](./y.md) [c](https://z) [d](#sec) ![i](p.png)")
    by = {l.target: l for l in links}
    assert by["/x.md"].is_absolute and not by["/x.md"].is_external
    assert by["./y.md"].is_absolute is False and by["./y.md"].is_external is False
    assert by["https://z"].is_external
    assert by["#sec"].is_anchor_only
    assert "p.png" not in by  # images skipped


# --------------------------------------------------------------------------- #
# Tier 1 — errors
# --------------------------------------------------------------------------- #
def test_clean_bundle_is_conformant(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "orders.md": CONCEPT_OK})
    res = _validate(root)
    assert res.conformant
    assert res.errors == []
    assert res.warnings == []


def test_E001_frontmatter_missing(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "# No frontmatter\n"})
    res = _validate(root)
    assert not res.conformant and "E001" in codes(res)


def test_E002_unterminated(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntype: X\nno close here\n"})
    res = _validate(root)
    assert "E002" in codes(res)


def test_E003_unparseable(make_bundle):
    # tab-indented mapping under a key is invalid in the mini parser and PyYAML alike
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\n\tbad:\n\t\t- x: [\n---\nbody"})
    res = _validate(root)
    assert "E003" in codes(res) or "E005" in codes(res) or "E004" in codes(res)


def test_E004_type_missing(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntitle: X\n---\nbody"})
    res = _validate(root)
    assert "E004" in codes(res) and not res.conformant


def test_E005_type_empty(make_bundle):
    for empty in ("", '""', "   ", "[]"):
        root = make_bundle({"index.md": ROOT_INDEX, "a.md": f"---\ntype: {empty}\n---\nbody"})
        res = _validate(root)
        assert "E005" in codes(res) or "E004" in codes(res), empty


def test_E006_nonroot_index_frontmatter(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "sub/index.md": "---\ntype: X\n---\n# Sub\n",
        "sub/a.md": CONCEPT_OK,
    })
    res = _validate(root)
    assert "E006" in codes(res) and not res.conformant


def test_E007_not_utf8(make_bundle, tmp_path):
    root = make_bundle({"index.md": ROOT_INDEX})
    with open(tmp_path / "bad.md", "wb") as fh:
        fh.write(b"---\ntype: X\n---\n\xff\xfe not utf8")
    res = _validate(root)
    assert "E007" in codes(res)


def test_root_index_okf_version_is_allowed(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK})
    res = _validate(root)
    assert "E006" not in codes(res)  # root index may carry okf_version


def test_reserved_files_not_checked_for_type(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "log.md": "# Log\n\n## 2026-05-22\n* **Creation**: init.\n",
        "a.md": CONCEPT_OK,
    })
    res = _validate(root)
    assert res.conformant


def test_default_ignores_readme(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "README.md": "# Readme, not a concept\n", "a.md": CONCEPT_OK})
    res = _validate(root)
    assert res.conformant  # README.md skipped by default
    # but with --no-default-ignores it becomes a concept and errors
    bundle = core.load_bundle(root, default_ignores=False)
    res2 = v.validate_bundle(bundle)
    assert "E001" in [f.code for f in res2.findings]


# --------------------------------------------------------------------------- #
# Tier 2 — warnings (never affect conformance)
# --------------------------------------------------------------------------- #
def test_warnings_do_not_break_conformance(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "a.md": "---\ntype: X\n---\n",  # missing title/description/timestamp + empty body
    })
    res = _validate(root)
    assert res.conformant  # still conformant!
    cs = codes(res)
    assert "W001" in cs and "W002" in cs and "W003" in cs and "W012" in cs


def test_W004_timestamp_not_iso(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntype: X\ntitle: A\ndescription: d\ntimestamp: yesterday\n---\nb"})
    res = _validate(root)
    assert "W004" in codes(res) and res.conformant


def test_W005_broken_link_but_no_default_relative_warning(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "b.md": CONCEPT_OK,  # exists, so the relative link below is NOT broken
        "a.md": CONCEPT_OK + "\nSee [missing](/nope.md) and [neighbor](./b.md).\n",
    })
    res = _validate(root)
    cs = codes(res)
    assert "W005" in cs               # /nope.md does not exist
    assert "W006" not in cs           # relative links are NOT a default warning anymore
    assert "Q009" not in cs           # ...and not in conformance profile at all
    assert res.conformant
    # under strict profile the relative ./b.md link surfaces as the opt-in Q009 quality lint
    strict = v.validate_bundle(core.load_bundle(root), profile="strict")
    assert "Q009" in codes(strict) and strict.conformant


def test_W015_link_escapes_bundle(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "sub/a.md": CONCEPT_OK + "\nEscapes: [x](../../../../etc/passwd).\n",
    })
    res = _validate(root)
    assert "W015" in codes(res) and res.conformant  # escape is a warning, never stat-ed


def test_W007_missing_root_index(make_bundle):
    root = make_bundle({"a.md": CONCEPT_OK})
    res = _validate(root)
    assert "W007" in codes(res) and res.conformant


def test_E008_log_date_not_iso_is_a_hard_error(make_bundle):
    # The non-ISO log date is now a CONFORMANCE error (§9.3 + §7's MUST) — the gap both
    # reference skills left as a mere warning.
    root = make_bundle({
        "index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
        "log.md": "# Log\n\n## 2026-05-01\n* y\n\n## 05/22/2026\n* z\n",
    })
    res = _validate(root)
    assert "E008" in codes(res) and not res.conformant


def test_W009_log_not_newest_first(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
        "log.md": "# Log\n\n## 2026-01-01\n* x\n\n## 2026-05-01\n* y\n",
    })
    res = _validate(root)
    assert "W009" in codes(res)   # ascending order -> warning
    assert res.conformant         # ...but still conformant (ordering is soft)


def test_prose_log_heading_is_not_flagged(make_bundle):
    # '## 2026 roadmap' is prose, not a date-shaped heading -> no E008 false positive.
    root = make_bundle({
        "index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
        "log.md": "# Log\n\n## 2026 roadmap\n* note\n\n## 2026-05-01\n* y\n",
    })
    res = _validate(root)
    assert "E008" not in codes(res) and res.conformant


def test_W013_tags_not_list(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "---\ntype: X\ntitle: A\ndescription: d\ntimestamp: 2026-05-28T14:30:00Z\ntags: sales\n---\nb"})
    res = _validate(root)
    assert "W013" in codes(res)


# --------------------------------------------------------------------------- #
# Tier 3 — quality (opt-in)
# --------------------------------------------------------------------------- #
def test_quality_only_in_strict_profile(make_bundle):
    files = {
        "index.md": ROOT_INDEX,
        ".okf.yml": "profile: strict\ntypes: [Table]\nconcrete_types: [Table]\n",
        # Widget is not in the registry (Q001) and is an orphan (Q003)
        "a.md": "---\ntype: Widget\ntitle: A\ndescription: d\ntimestamp: 2026-05-28T14:30:00Z\n---\nbody no links\n",
        # Table is concrete but has no resource (Q004); also an orphan (Q003)
        "b.md": "---\ntype: Table\ntitle: B\ndescription: d\ntimestamp: 2026-05-28T14:30:00Z\n---\nbody no links\n",
    }
    root = make_bundle(files)
    cfg = v.ProjectConfig.load(root)
    bundle = core.load_bundle(root)
    # conformance profile: no Q codes
    res = v.validate_bundle(bundle, profile="conformance")
    assert not any(c.startswith("Q") for c in codes(res))
    # strict: Q001 (Widget not in registry), Q003 (orphan), Q004 (Table concrete missing resource)
    res2 = v.validate_bundle(bundle, profile="strict", config=cfg)
    cs = codes(res2)
    assert "Q001" in cs and "Q003" in cs and "Q004" in cs
    assert res2.conformant  # quality lints never break conformance


def test_strict_flag_exit_on_warnings(make_bundle):
    import types
    root = make_bundle({"a.md": CONCEPT_OK})  # missing root index => W007
    args = types.SimpleNamespace(path=root, format="json", profile="conformance", strict=True,
                                 pedantic=False, no_links=False, no_color=True,
                                 no_default_ignores=False, ignore=[])
    assert v.run(args) == 1  # warnings + --strict => non-zero


def test_json_output_shape(make_bundle, capsys):
    import types
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK})
    args = types.SimpleNamespace(path=root, format="json", profile="conformance", strict=False,
                                 pedantic=False, no_links=False, no_color=True,
                                 no_default_ignores=False, ignore=[])
    rc = v.run(args)
    out = capsys.readouterr().out
    import json
    data = json.loads(out)
    assert rc == 0 and data["conformant"] is True
    assert set(data["summary"]) == {"errors", "warnings", "quality"}


# --------------------------------------------------------------------------- #
# Acceptance bias: real-world producer quirks must stay conformant (no over-rejection)
# --------------------------------------------------------------------------- #
GA4_STYLE = (
    "---\n"
    "type: BigQuery Dataset\n"
    "resource: https://bigquery.googleapis.com/v2/projects/p/datasets/ga4\n"
    "title: GA4 sample\n"
    "description: A sample of obfuscated Google Analytics BigQuery event export data for\n"
    "  three months from the Google Merchandise Store is available as a public dataset\n"
    "  in BigQuery.\n"
    "tags:\n- ecommerce\n- web analytics\n"
    "timestamp: '2026-05-28T22:49:59+00:00'\n"
    "---\n# Overview\nUses [events](../tables/events_.md) relative link.\n"
)


def test_folded_scalar_and_quirks_are_conformant(make_bundle):
    # multi-line folded description + col-0 block list + quoted ISO+offset + relative link
    # + scalar-comma tags (the stackoverflow quirk) + unknown type -> conformant, warnings only.
    root = make_bundle({
        "index.md": ROOT_INDEX,
        "datasets/ga4.md": GA4_STYLE,
        "datasets/so.md": ("---\ntype: BigQuery Dataset\ntitle: SO\ndescription: d\n"
                           "timestamp: 2026-05-28T14:30:00Z\ntags: Stack Overflow, public data, Q&A\n"
                           "---\nbody [x](/datasets/ga4.md)\n"),
    })
    res = _validate(root)
    assert res.conformant, codes(res)            # NO false E003 on the folded scalar
    assert "E003" not in codes(res)
    assert "W013" in codes(res)                   # scalar-comma tags -> warning, not error


def test_Q007_unsafe_path_segment(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": CONCEPT_OK, "weird name!.md": CONCEPT_OK})
    strict = v.validate_bundle(core.load_bundle(root), profile="strict")
    assert "Q007" in codes(strict) and strict.conformant


def test_Q008_duplicate_concept_id_case_insensitive(make_bundle, tmp_path):
    # simulate a case-insensitive collision without relying on the host filesystem
    root = make_bundle({"index.md": ROOT_INDEX, "Orders.md": CONCEPT_OK, "x.md": CONCEPT_OK})
    bundle = core.load_bundle(root)
    # inject a colliding rel_path
    import okf_core
    dup = okf_core.Document(path=str(tmp_path / "orders.md"), rel_path="orders.md", kind="concept")
    dup.frontmatter = {"type": "Table"}
    bundle.documents.append(dup)
    strict = v.validate_bundle(bundle, profile="strict")
    assert "Q008" in codes(strict)


def test_pedantic_promotes_reserved_warnings_to_errors(make_bundle):
    root = make_bundle({
        "index.md": ROOT_INDEX, "a.md": CONCEPT_OK,
        "log.md": "# Log\n\n## 2026-01-01\n* x\n\n## 2026-05-01\n* y\n",  # ascending -> W009
    })
    normal = _validate(root)
    assert normal.conformant and "W009" in codes(normal)
    ped = v.validate_bundle(core.load_bundle(root), pedantic=True)
    assert not ped.conformant and "W009" in [f.code for f in ped.errors]


def test_findings_carry_spec_section(make_bundle):
    root = make_bundle({"index.md": ROOT_INDEX, "a.md": "# no fm\n"})
    res = _validate(root)
    e001 = [f for f in res.findings if f.code == "E001"][0]
    assert e001.spec == "§9" and e001.to_dict()["spec"] == "§9"
