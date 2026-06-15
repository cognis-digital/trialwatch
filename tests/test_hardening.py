"""Tests for hardened error handling and edge cases in TRIALWATCH."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from trialwatch.core import (
    load_trials,
    load_trials_from_obj,
    diff_trials,
)
from trialwatch.cli import main


# ---------------------------------------------------------------------------
# core: load_trials_from_obj edge cases
# ---------------------------------------------------------------------------

def test_load_from_obj_empty_list():
    """An empty list returns an empty dict, not an error."""
    result = load_trials_from_obj([])
    assert result == {}


def test_load_from_obj_skips_bad_records_keeps_good():
    """Records missing an NCT id are skipped; valid records are still loaded."""
    data = [
        {"title": "no id here"},           # missing nct_id — skipped
        {"nct_id": "NCT00000001", "title": "Good Trial"},
    ]
    result = load_trials_from_obj(data)
    assert "NCT00000001" in result
    assert len(result) == 1


def test_load_from_obj_all_bad_records_raises():
    """If every record is invalid, raise ValueError with a useful message."""
    data = [{"title": "bad1"}, {"title": "bad2"}]
    with pytest.raises(ValueError, match="no valid trial records"):
        load_trials_from_obj(data)


def test_load_from_obj_non_dict_non_list_raises():
    """A bare string/number is not a valid snapshot."""
    with pytest.raises(ValueError, match="snapshot must be"):
        load_trials_from_obj("not a list or dict")


# ---------------------------------------------------------------------------
# core: load_trials — file I/O errors
# ---------------------------------------------------------------------------

def test_load_trials_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_trials("/nonexistent/path/to/file_xyz.json")


def test_load_trials_bad_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json }", encoding="utf-8")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        load_trials(str(bad))


# ---------------------------------------------------------------------------
# core: diff_trials — invalid arguments
# ---------------------------------------------------------------------------

def test_diff_trials_negative_threshold_raises():
    with pytest.raises(ValueError, match="enrollment_pct_threshold must be >= 0"):
        diff_trials({}, {}, enrollment_pct_threshold=-1.0)


def test_diff_trials_wrong_type_raises():
    with pytest.raises(TypeError, match="must be dicts"):
        diff_trials([], {})  # type: ignore[arg-type]


def test_diff_trials_empty_snapshots():
    """Diffing two empty snapshots produces zero changes."""
    report = diff_trials({}, {})
    assert report.total_changes() == 0
    assert report.base_count == 0
    assert report.new_count == 0


# ---------------------------------------------------------------------------
# cli: validation and error exit codes
# ---------------------------------------------------------------------------

def test_cli_negative_threshold_returns_exit2(capsys):
    rc = main(["diff", "old.json", "new.json", "--enrollment-threshold", "-5"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "enrollment-threshold" in err or "enrollment_pct_threshold" in err or ">= 0" in err


def test_cli_malformed_json_returns_exit2(capsys, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text('[{"nct_id": "NCT1"}]', encoding="utf-8")
    rc = main(["diff", str(bad), str(good)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_mcp_server_importable():
    """mcp_server module must import without raising ImportError."""
    import importlib
    mod = importlib.import_module("trialwatch.mcp_server")
    assert callable(mod.serve)
