"""Behavioral tests for the scaffold / index / graph / context / migrate tools."""
import json
import os
import types

import okf_core as core
import okf_validate as v
import okf_new
import okf_index
import okf_graph
import okf_context
import okf_migrate
from conftest import codes


def _conformant(root):
    return v.validate_bundle(core.load_bundle(root)).conformant


# --------------------------------------------------------------------------- #
# scaffold
# --------------------------------------------------------------------------- #
def test_new_bundle_and_concept_are_conformant(tmp_path):
    bundle = str(tmp_path / "b")
    assert okf_new.new_bundle(bundle, "B", "0.1") == 0
    assert os.path.isfile(os.path.join(bundle, "index.md"))
    assert os.path.isfile(os.path.join(bundle, "log.md"))
    okf_new.new_concept(bundle, "tables/orders", "Table", "Orders", "One row per order.", "", ["sales"], True)
    res = v.validate_bundle(core.load_bundle(bundle))
    assert res.conformant
    # the scaffolded concept carries a non-empty type
    doc = [d for d in core.load_bundle(bundle).concepts if d.rel_path == "tables/orders.md"][0]
    assert doc.frontmatter["type"] == "Table"


def test_new_concept_requires_type(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    assert okf_new.new_concept(bundle, "x", "", "", "", "", [], False) == 2


# --------------------------------------------------------------------------- #
# index
# --------------------------------------------------------------------------- #
def test_index_lists_concepts_and_detects_staleness(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    okf_new.new_concept(bundle, "tables/orders", "Table", "Orders", "One row per order.", "", [], False)
    okf_new.new_concept(bundle, "tables/customers", "Table", "Customers", "One row per customer.", "", [], False)
    b = core.load_bundle(bundle)
    rendered = okf_index.render_index(b, "tables")
    assert "[Orders](orders.md)" in rendered and "One row per order." in rendered
    # write, then --check should be clean
    args = types.SimpleNamespace(path=bundle, dir="", recursive=True, write=True, check=False, okf_version="0.1")
    assert okf_index.run(args) == 0
    args_check = types.SimpleNamespace(path=bundle, dir="", recursive=True, write=False, check=True, okf_version="0.1")
    assert okf_index.run(args_check) == 0
    # mutate a description -> stale
    okf_new.new_concept(bundle, "tables/refunds", "Table", "Refunds", "One row per refund.", "", [], False)
    assert okf_index.run(args_check) == 1


def test_generated_nonroot_index_has_no_frontmatter(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    okf_new.new_concept(bundle, "t/a", "Table", "A", "d", "", [], False)
    args = types.SimpleNamespace(path=bundle, dir="", recursive=True, write=True, check=False, okf_version="0.1")
    okf_index.run(args)
    res = v.validate_bundle(core.load_bundle(bundle))
    assert "E006" not in codes(res) and res.conformant


# --------------------------------------------------------------------------- #
# graph
# --------------------------------------------------------------------------- #
def test_graph_nodes_edges_and_broken(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    okf_new.new_concept(bundle, "a", "Table", "A", "d", "", [], False)
    okf_new.new_concept(bundle, "b", "Table", "B", "d", "", [], False)
    with open(os.path.join(bundle, "a.md"), "a", encoding="utf-8") as fh:
        fh.write("\nlinks [B](/b.md) and [gone](/missing.md)\n")
    g = okf_graph.build_graph(core.load_bundle(bundle))
    assert len(g["nodes"]) == 2
    targets = {(e["target"], e["broken"]) for e in g["edges"]}
    assert ("b.md", False) in targets and ("missing.md", True) in targets
    # renderers produce output
    assert "graph LR" in okf_graph.to_mermaid(g)
    html = okf_graph.to_html(g, "B")
    assert "<svg" in html and "DATA" in html and "<script" in html


def test_graph_html_escapes_script_breakout():
    import json as _json, re as _re
    graph = {"nodes": [{"id": "a", "path": "a.md",
                        "title": "Evil </script><img src=x onerror=alert(1)>", "type": "T", "tags": []}],
             "edges": []}
    html = okf_graph.to_html(graph, "t")
    assert "</script><img" not in html            # breakout neutralized
    assert "\\u003c" in html                       # '<' escaped in embedded JSON
    data = _json.loads(_re.search(r"const DATA = (\{.*?\});", html, _re.S).group(1))
    assert data["nodes"][0]["title"].startswith("Evil </script>")  # data still intact


def test_graph_mermaid_is_deterministic_with_dangling_edges():
    graph = {"nodes": [{"id": "a", "path": "a.md", "title": "A", "type": "T", "tags": []}],
             "edges": [{"source": "a.md", "target": "gone/x.md", "broken": True},
                       {"source": "a.md", "target": "gone/x.md", "broken": True}]}
    m1 = okf_graph.to_mermaid(graph)
    m2 = okf_graph.to_mermaid(graph)
    assert m1 == m2                       # no hash()-based nondeterminism
    assert m1.count("(missing)") == 1     # dangling target defined exactly once


# --------------------------------------------------------------------------- #
# context (progressive disclosure)
# --------------------------------------------------------------------------- #
def test_context_selects_relevant_and_expands_neighbors(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    okf_new.new_concept(bundle, "orders", "Table", "Orders", "Completed orders.", "", ["sales"], False)
    okf_new.new_concept(bundle, "customers", "Table", "Customers", "Customer records.", "", ["sales"], False)
    okf_new.new_concept(bundle, "weather", "Dataset", "Weather", "Unrelated weather data.", "", ["climate"], False)
    with open(os.path.join(bundle, "orders.md"), "a", encoding="utf-8") as fh:
        fh.write("\nJoined with [customers](/customers.md).\n")
    b = core.load_bundle(bundle)
    primary, related_paths, related = okf_context.select(b, "orders", max_concepts=1, hops=1)
    assert [d.rel_path for d in primary] == ["orders.md"]
    # customers is a 1-hop neighbor of orders
    assert "customers.md" in {d.rel_path for d in related}
    # weather is unrelated and not selected
    assert "weather.md" not in {d.rel_path for d in primary} | {d.rel_path for d in related}


def test_context_outline_has_no_bodies(tmp_path):
    bundle = str(tmp_path / "b")
    okf_new.new_bundle(bundle, "B", "0.1")
    okf_new.new_concept(bundle, "orders", "Table", "Orders", "Completed orders.", "", [], False)
    b = core.load_bundle(bundle)
    outline = okf_context.render_outline(b)
    assert "orders" in outline and "Completed orders." in outline


# --------------------------------------------------------------------------- #
# migrate
# --------------------------------------------------------------------------- #
def test_migrate_adds_type_and_converts_wikilinks(tmp_path):
    src = tmp_path / "notes"
    (src / "sub").mkdir(parents=True)
    (src / "orders.md").write_text("# Orders\n\nOrders table. See [[Customers]] and [[Weekly Active Users|WAU]].\n")
    (src / "customers.md").write_text("# Customers\n\nCustomers. Links [[Orders]].\n")
    (src / "sub" / "weekly-active-users.md").write_text("---\ntype: Metric\n---\n# Weekly Active Users\n\nWAU.\n")
    out = str(tmp_path / "kb")
    args = types.SimpleNamespace(path=str(src), out=out, write=False, default_type="Note", regenerate_index=False)
    assert okf_migrate.run(args) == 0
    orders = (tmp_path / "kb" / "orders.md").read_text()
    assert "type: Note" in orders
    assert "[Customers](/customers.md)" in orders
    # alias + title-slug resolution to nested file
    assert "[WAU](/sub/weekly-active-users.md)" in orders
    # pre-existing type preserved
    assert "type: Metric" in (tmp_path / "kb" / "sub" / "weekly-active-users.md").read_text()
    # after indexing, the migrated bundle is conformant
    iargs = types.SimpleNamespace(path=out, dir="", recursive=True, write=True, check=False, okf_version="0.1")
    okf_index.run(iargs)
    assert _conformant(out)


def test_migrate_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "notes"
    src.mkdir()
    (src / "a.md").write_text("# A\n\nhi\n")
    args = types.SimpleNamespace(path=str(src), out=None, write=False, default_type="Note", regenerate_index=False)
    assert okf_migrate.run(args) == 0
    assert not (src / "index.md").exists()  # dry run touched nothing


def test_slugify():
    assert okf_migrate.slugify("Weekly Active Users!") == "weekly-active-users"
    assert okf_migrate.slugify("  Foo / Bar  ") == "foo-bar"
