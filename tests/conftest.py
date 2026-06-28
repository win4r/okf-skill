"""Pytest configuration: make the plugin scripts importable and provide bundle helpers."""
import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "okf-plugin", "scripts")
sys.path.insert(0, SCRIPTS)


def write_bundle(root, files):
    """Create a bundle on disk from a {relative_path: content} mapping. Returns root path."""
    for rel, content in files.items():
        dest = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dest) or str(root), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
    return str(root)


@pytest.fixture
def make_bundle(tmp_path):
    def _make(files):
        return write_bundle(tmp_path, files)
    return _make


def codes(result):
    return [f.code for f in result.findings]


CONCEPT_OK = (
    "---\n"
    "type: Table\n"
    "title: Orders\n"
    "description: One row per completed order.\n"
    "timestamp: 2026-05-28T14:30:00Z\n"
    "---\n"
    "# Overview\nOrders table.\n"
)

ROOT_INDEX = '---\nokf_version: "0.1"\n---\n# Bundle\n* [Orders](orders.md) - orders\n'
