"""Smoke tests for TRIALWATCH - run the engine on the bundled demo."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from trialwatch import (  # noqa: E402
    TOOL_NAME,
    TOOL_VERSION,
    load_trials,
    load_trials_from_obj,
    normalize_trial,
    diff_trials,
)
from trialwatch.cli import main  # noqa: E402

DEMO = os.path.join(os.path.dirname(__file__), "..", "demos", "01-basic")
OLD = os.path.join(DEMO, "snapshot_old.json")
NEW = os.path.join(DEMO, "snapshot_new.json")


def test_metadata():
    assert TOOL_NAME == "trialwatch"
    assert TOOL_VERSION.count(".") == 2


def test_normalize_aliases():
    t = normalize_trial(
        {"nctId": "NCT99", "briefTitle": "X", "overallStatus": "Recruiting",
         "enrollmentCount": "50"}
    )
    assert t.nct_id == "NCT99"
    assert t.title == "X"
    assert t.status == "Recruiting"
    assert t.enrollment == 50  # coerced from string


def test_normalize_requires_id():
    with pytest.raises(ValueError):
        normalize_trial({"title": "no id"})


def test_load_demo():
    base = load_trials(OLD)
    new = load_trials(NEW)
    assert len(base) == 4
    assert len(new) == 4
    assert "NCT01000001" in base


def test_diff_detects_expected_changes():
    base = load_trials(OLD)
    new = load_trials(NEW)
    report = diff_trials(base, new)

    kinds = {(c.nct_id, c.kind) for c in report.changes}
    # Terminated status -> critical
    assert ("NCT01000001", "status") in kinds
    # Enrollment 100 -> 300 (+200%)
    assert ("NCT01000002", "enrollment") in kinds
    # Phase 1 -> Phase 2 and completion date change
    assert ("NCT01000003", "phase") in kinds
    assert ("NCT01000003", "completion") in kinds
    # Removed trial
    assert ("NCT01000004", "removed") in kinds
    # Added trial
    assert ("NCT01000005", "added") in kinds


def test_severity_classification():
    base = load_trials(OLD)
    new = load_trials(NEW)
    report = diff_trials(base, new)
    crit = [c for c in report.changes if c.nct_id == "NCT01000001" and c.kind == "status"]
    assert crit and crit[0].severity == "critical"
    enr = [c for c in report.changes if c.nct_id == "NCT01000002" and c.kind == "enrollment"]
    assert enr and enr[0].severity == "warning"  # +200% >= 20%


def test_no_changes_when_identical():
    base = load_trials(OLD)
    report = diff_trials(base, dict(base))
    assert report.total_changes() == 0
    assert not report.has_findings("info")


def test_enrollment_threshold_escalation():
    a = load_trials_from_obj([{"nct_id": "N1", "enrollment": 100}])
    b = load_trials_from_obj([{"nct_id": "N1", "enrollment": 110}])
    # 10% swing, default threshold 20 -> info
    r = diff_trials(a, b)
    assert r.changes[0].severity == "info"
    # threshold lowered to 5 -> warning
    r2 = diff_trials(a, b, enrollment_pct_threshold=5.0)
    assert r2.changes[0].severity == "warning"


def test_cli_json_exit_nonzero(capsys):
    rc = main(["diff", OLD, NEW, "--format", "json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["total_changes"] >= 6
    assert payload["by_severity"]["critical"] >= 1
    # critical change present -> non-zero exit under default --fail-on warning
    assert rc == 1


def test_cli_table_runs(capsys):
    rc = main(["diff", OLD, NEW])
    out = capsys.readouterr().out
    assert "TRIALWATCH diff" in out
    assert "[CRIT]" in out
    assert rc == 1


def test_cli_no_command_returns_usage_code(capsys):
    rc = main([])
    assert rc == 2


def test_cli_missing_file(capsys):
    rc = main(["diff", "does_not_exist.json", NEW])
    assert rc == 2
