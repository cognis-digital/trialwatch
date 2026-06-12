"""Core engine for TRIALWATCH.

Parses clinical-trial snapshots (JSON), normalizes the fields that matter,
and computes a structured diff between an old and new snapshot.

No third-party dependencies. Pure standard library.

Input format
------------
A snapshot is JSON: either a list of trial objects, or an object with a
"studies" / "trials" key holding the list. Each trial object is flexible -
we accept common ClinicalTrials.gov-ish field names and aliases:

    {
        "nct_id": "NCT01234567",      # or "id" / "nctId"
        "title": "...",                # or "brief_title" / "briefTitle"
        "status": "Recruiting",        # or "overall_status" / "overallStatus"
        "phase": "Phase 2",            # or "phases"
        "enrollment": 240,             # int-ish
        "sponsor": "Acme Bio",         # or "lead_sponsor"
        "completion_date": "2026-12",  # or "primary_completion_date"
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Severity ranking used for sorting and for the CI exit decision.
SEVERITY_ORDER = {"critical": 3, "warning": 2, "info": 1}

# Field aliases: canonical name -> list of accepted source keys.
_ALIASES = {
    "nct_id": ["nct_id", "nctId", "id", "NCTId"],
    "title": ["title", "brief_title", "briefTitle", "official_title"],
    "status": ["status", "overall_status", "overallStatus"],
    "phase": ["phase", "phases"],
    "enrollment": ["enrollment", "enrollment_count", "enrollmentCount"],
    "sponsor": ["sponsor", "lead_sponsor", "leadSponsor"],
    "completion_date": [
        "completion_date",
        "completionDate",
        "primary_completion_date",
        "primaryCompletionDate",
    ],
}

# Statuses that typically mean a trial has stopped early / unexpectedly.
_ADVERSE_STATUSES = {
    "terminated",
    "suspended",
    "withdrawn",
    "no longer available",
}
# Statuses representing a normal end-of-life.
_TERMINAL_STATUSES = {"completed"}


@dataclass
class Trial:
    """A normalized clinical-trial record."""

    nct_id: str
    title: str = ""
    status: str = ""
    phase: str = ""
    enrollment: Optional[int] = None
    sponsor: str = ""
    completion_date: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nct_id": self.nct_id,
            "title": self.title,
            "status": self.status,
            "phase": self.phase,
            "enrollment": self.enrollment,
            "sponsor": self.sponsor,
            "completion_date": self.completion_date,
        }


@dataclass
class Change:
    """A single detected change for one trial."""

    nct_id: str
    title: str
    kind: str          # added | removed | status | enrollment | phase | sponsor | completion
    field: str
    old: Any
    new: Any
    severity: str      # critical | warning | info
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nct_id": self.nct_id,
            "title": self.title,
            "kind": self.kind,
            "field": self.field,
            "old": self.old,
            "new": self.new,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class DiffReport:
    """Result of diffing two snapshots."""

    changes: List[Change] = field(default_factory=list)
    base_count: int = 0
    new_count: int = 0

    def total_changes(self) -> int:
        return len(self.changes)

    def by_severity(self) -> Dict[str, int]:
        counts = {"critical": 0, "warning": 0, "info": 0}
        for c in self.changes:
            counts[c.severity] = counts.get(c.severity, 0) + 1
        return counts

    def has_findings(self, min_severity: str = "info") -> bool:
        threshold = SEVERITY_ORDER.get(min_severity, 1)
        return any(SEVERITY_ORDER.get(c.severity, 0) >= threshold for c in self.changes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_count": self.base_count,
            "new_count": self.new_count,
            "total_changes": self.total_changes(),
            "by_severity": self.by_severity(),
            "changes": [c.to_dict() for c in self.changes],
        }


def _pick(obj: Dict[str, Any], canonical: str) -> Any:
    for key in _ALIASES[canonical]:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value).strip()


def normalize_trial(obj: Dict[str, Any]) -> Trial:
    """Convert a raw trial dict (any accepted alias scheme) into a Trial."""
    if not isinstance(obj, dict):
        raise ValueError("trial record must be an object/dict")
    nct = _pick(obj, "nct_id")
    if nct is None:
        raise ValueError("trial record missing an NCT id (nct_id/id/nctId)")
    return Trial(
        nct_id=_stringify(nct),
        title=_stringify(_pick(obj, "title")),
        status=_stringify(_pick(obj, "status")),
        phase=_stringify(_pick(obj, "phase")),
        enrollment=_coerce_int(_pick(obj, "enrollment")),
        sponsor=_stringify(_pick(obj, "sponsor")),
        completion_date=_stringify(_pick(obj, "completion_date")),
        raw=obj,
    )


def load_trials_from_obj(data: Any) -> Dict[str, Trial]:
    """Build a {nct_id: Trial} map from already-parsed JSON data."""
    if isinstance(data, dict):
        for key in ("studies", "trials", "records", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            # A single trial object.
            data = [data]
    if not isinstance(data, list):
        raise ValueError("snapshot must be a list of trials or contain one")
    trials: Dict[str, Trial] = {}
    for item in data:
        trial = normalize_trial(item)
        trials[trial.nct_id] = trial
    return trials


def load_trials(path: str) -> Dict[str, Trial]:
    """Load a snapshot file and return a {nct_id: Trial} map."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return load_trials_from_obj(data)


def _status_severity(old: str, new: str) -> str:
    n = new.strip().lower()
    if n in _ADVERSE_STATUSES:
        return "critical"
    if n in _TERMINAL_STATUSES:
        return "warning"
    return "warning"


def _enrollment_change(old: Optional[int], new: Optional[int], pct_threshold: float):
    """Return (changed, severity, pct) for an enrollment delta."""
    if old == new:
        return (False, "info", 0.0)
    if old is None or new is None:
        return (True, "info", 0.0)
    if old == 0:
        pct = 100.0 if new != 0 else 0.0
    else:
        pct = abs(new - old) / abs(old) * 100.0
    severity = "warning" if pct >= pct_threshold else "info"
    return (True, severity, pct)


def diff_trials(
    base: Dict[str, Trial],
    new: Dict[str, Trial],
    enrollment_pct_threshold: float = 20.0,
) -> DiffReport:
    """Compute a structured diff between two {nct_id: Trial} maps.

    enrollment_pct_threshold: enrollment swings >= this percent are flagged
    as 'warning' rather than 'info'.
    """
    report = DiffReport(base_count=len(base), new_count=len(new))
    base_ids = set(base)
    new_ids = set(new)

    # Added trials.
    for nct in sorted(new_ids - base_ids):
        t = new[nct]
        report.changes.append(
            Change(
                nct_id=nct,
                title=t.title,
                kind="added",
                field="trial",
                old=None,
                new=t.status or "present",
                severity="info",
                message="New trial appeared: {} ({})".format(
                    nct, t.status or "unknown status"
                ),
            )
        )

    # Removed trials.
    for nct in sorted(base_ids - new_ids):
        t = base[nct]
        report.changes.append(
            Change(
                nct_id=nct,
                title=t.title,
                kind="removed",
                field="trial",
                old=t.status or "present",
                new=None,
                severity="warning",
                message="Trial removed from feed: {}".format(nct),
            )
        )

    # Modified trials.
    for nct in sorted(base_ids & new_ids):
        ob, nb = base[nct], new[nct]
        title = nb.title or ob.title

        if ob.status != nb.status:
            report.changes.append(
                Change(
                    nct_id=nct,
                    title=title,
                    kind="status",
                    field="status",
                    old=ob.status,
                    new=nb.status,
                    severity=_status_severity(ob.status, nb.status),
                    message="Status: '{}' -> '{}'".format(
                        ob.status or "(none)", nb.status or "(none)"
                    ),
                )
            )

        changed, sev, pct = _enrollment_change(
            ob.enrollment, nb.enrollment, enrollment_pct_threshold
        )
        if changed:
            pct_txt = " ({:+.0f}%)".format(
                pct if (nb.enrollment or 0) >= (ob.enrollment or 0) else -pct
            ) if (ob.enrollment is not None and nb.enrollment is not None) else ""
            report.changes.append(
                Change(
                    nct_id=nct,
                    title=title,
                    kind="enrollment",
                    field="enrollment",
                    old=ob.enrollment,
                    new=nb.enrollment,
                    severity=sev,
                    message="Enrollment: {} -> {}{}".format(
                        ob.enrollment, nb.enrollment, pct_txt
                    ),
                )
            )

        if ob.phase != nb.phase:
            report.changes.append(
                Change(
                    nct_id=nct,
                    title=title,
                    kind="phase",
                    field="phase",
                    old=ob.phase,
                    new=nb.phase,
                    severity="info",
                    message="Phase: '{}' -> '{}'".format(
                        ob.phase or "(none)", nb.phase or "(none)"
                    ),
                )
            )

        if ob.sponsor != nb.sponsor:
            report.changes.append(
                Change(
                    nct_id=nct,
                    title=title,
                    kind="sponsor",
                    field="sponsor",
                    old=ob.sponsor,
                    new=nb.sponsor,
                    severity="info",
                    message="Sponsor: '{}' -> '{}'".format(
                        ob.sponsor or "(none)", nb.sponsor or "(none)"
                    ),
                )
            )

        if ob.completion_date != nb.completion_date:
            report.changes.append(
                Change(
                    nct_id=nct,
                    title=title,
                    kind="completion",
                    field="completion_date",
                    old=ob.completion_date,
                    new=nb.completion_date,
                    severity="info",
                    message="Completion date: '{}' -> '{}'".format(
                        ob.completion_date or "(none)",
                        nb.completion_date or "(none)",
                    ),
                )
            )

    report.changes.sort(
        key=lambda c: (-SEVERITY_ORDER.get(c.severity, 0), c.nct_id, c.kind)
    )
    return report
