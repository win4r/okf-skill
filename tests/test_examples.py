"""Corpus tests over the shipped example bundles — the load-bearing 'is the green check real' check.

valid bundles must be conformant; each invalid/<Ecode>-* bundle must be non-conformant AND
surface exactly that error code.
"""
import os

import pytest

import okf_core as core
import okf_validate as v

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALID = os.path.join(ROOT, "examples", "valid")
INVALID = os.path.join(ROOT, "examples", "invalid")


def _bundles(base):
    if not os.path.isdir(base):
        return []
    return [os.path.join(base, d) for d in sorted(os.listdir(base))
            if os.path.isdir(os.path.join(base, d))]


@pytest.mark.parametrize("path", _bundles(VALID), ids=lambda p: os.path.basename(p))
def test_valid_bundles_are_conformant(path):
    res = v.validate_bundle(core.load_bundle(path))
    assert res.conformant, [f"{f.code} {f.path}: {f.message}" for f in res.errors]


def test_showcase_is_strict_clean():
    """The golden bundle must pass --strict with zero warnings (stays exemplary over time)."""
    path = os.path.join(VALID, "acme-analytics")
    res = v.validate_bundle(core.load_bundle(path))
    assert res.conformant and not res.warnings, [f.code for f in res.warnings]


@pytest.mark.parametrize("path", _bundles(INVALID), ids=lambda p: os.path.basename(p))
def test_invalid_bundles_fail_with_their_code(path):
    expected = os.path.basename(path).split("-", 1)[0]  # e.g. "E004"
    res = v.validate_bundle(core.load_bundle(path))
    codes = [f.code for f in res.findings]
    assert not res.conformant, f"{path} should be non-conformant"
    assert expected in codes, f"{path}: expected {expected}, got {codes}"


def test_permissive_quirks_is_conformant_with_warnings():
    """Proves the permissive consumption model: quirks → warnings, never errors."""
    path = os.path.join(VALID, "permissive-quirks")
    res = v.validate_bundle(core.load_bundle(path))
    assert res.conformant
    assert res.warnings  # it intentionally carries warnings
    assert "E003" not in [f.code for f in res.findings]  # folded scalar must NOT false-error
