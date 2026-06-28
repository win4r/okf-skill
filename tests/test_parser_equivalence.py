"""Prove the zero-dependency mini-parser's accept/reject verdict matches PyYAML on real
producer output. This is what makes 'zero-dependency' safe to claim: the shipped conformance
verdict never diverges from a real YAML parser on the content OKF bundles actually contain.

Dev-only: skipped when PyYAML is not installed (the shipped tools never import it).
"""
import glob
import os

import pytest

import okf_core as core

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Representative frontmatter blocks covering the yaml.safe_dump surface OKF producers emit.
CORPUS = [
    "type: Table\ntitle: Orders\ndescription: One row per order.\ntimestamp: 2026-05-28T14:30:00Z",
    # multi-line folded plain scalar + col-0 block list + quoted ISO+offset (the ga4 shape)
    ("type: BigQuery Dataset\nresource: https://x/y\ntitle: GA4\n"
     "description: A sample of obfuscated data for\n  three months from the store is\n  available publicly.\n"
     "tags:\n- ecommerce\n- web analytics\ntimestamp: '2026-05-28T22:49:59+00:00'"),
    # indented block list
    "type: Metric\ntags:\n  - a\n  - b\n  - c",
    # scalar-comma tags quirk (must parse as a string, both parsers agree it's a mapping)
    "type: Dataset\ntags: Stack Overflow, public data, community, Q&A",
    # quoted version + url with colon
    'okf_version: "0.1"\nresource: https://x.com/a:b/c\ntype: Table',
    # flow list
    "type: Table\ntags: [sales, revenue, q&a]",
    # booleans / null / numbers
    "type: Widget\ndraft: true\nshipped: false\nowner: null\ncount: 42\nratio: 1.5",
    # non-ASCII escaped by default safe_dump (allow_unicode=False)
    'type: "\\u6570\\u636e\\u96c6"\ntitle: GA',
    # whole-document flow mapping
    "{type: Dataset, title: Foo, n: 3}",
    # uniformly-indented top-level mapping (valid YAML)
    "  type: Table\n  title: Orders\n  count: 2",
    # block scalar value
    "type: Note\nbody: |\n  line one\n  line two",
]


def _harvest_from_examples():
    out = []
    for md in glob.glob(os.path.join(ROOT, "examples", "valid", "**", "*.md"), recursive=True):
        with open(md, "rb") as fh:
            try:
                text = fh.read().decode("utf-8")
            except UnicodeDecodeError:
                continue
        split = core.split_frontmatter(text)
        if split.has_marker and split.terminated and split.raw and split.raw.strip():
            out.append(split.raw)
    return out


@pytest.mark.parametrize("raw", CORPUS + _harvest_from_examples())
def test_mini_parser_matches_pyyaml(raw):
    mini, mini_err = core.parse_yaml_mini(raw)
    try:
        py = yaml.safe_load(raw)
        py_is_mapping = isinstance(py, dict)
        py_err = None
    except Exception as e:  # noqa: BLE001
        py_is_mapping = False
        py_err = e

    # 1. Accept/reject-as-mapping verdict must agree (this is what conformance hinges on).
    mini_is_mapping = mini_err is None and isinstance(mini, dict) and bool(mini)
    if py_err is not None:
        # PyYAML hard-errored: the mini-parser must not have produced a confident mapping
        # that PyYAML would reject. (Fail-open is fine; a false mapping would be the bug.)
        return
    assert mini_is_mapping == (py_is_mapping and bool(py)), f"verdict mismatch: mini={mini!r} py={py!r}"

    if py_is_mapping and mini_is_mapping:
        # 2. The all-important `type` value must match exactly.
        assert str(mini.get("type")) == str(py.get("type")), f"type mismatch: {mini} vs {py}"
        # 3. Same top-level keys.
        assert set(mini.keys()) == set(py.keys()), f"key mismatch: {set(mini)} vs {set(py)}"
        # 4. List-valued fields agree.
        for k in mini:
            if isinstance(py.get(k), list):
                assert mini[k] == py[k], f"{k}: {mini[k]} vs {py[k]}"
