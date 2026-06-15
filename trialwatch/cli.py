"""Command-line interface for TRIALWATCH.

Examples
--------
  # Diff two snapshots, human-readable table:
  trialwatch diff old.json new.json

  # JSON output for piping into CI / jq:
  trialwatch diff old.json new.json --format json

  # Only fail CI on warning-or-worse changes (status/removed/big enrollment):
  trialwatch diff old.json new.json --fail-on warning

  # Tune what counts as a big enrollment swing (default 20%):
  trialwatch diff old.json new.json --enrollment-threshold 50

Exit codes
----------
  0  no findings at/above the --fail-on severity
  1  findings detected (use in a CI gate / cron alert)
  2  usage / input error
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import load_trials, diff_trials, SEVERITY_ORDER

_SEV_TAG = {"critical": "[CRIT]", "warning": "[WARN]", "info": "[info]"}


def _render_table(report, fail_on: str) -> str:
    lines: List[str] = []
    counts = report.by_severity()
    lines.append(
        "TRIALWATCH diff: {} -> {} trials | {} change(s) "
        "[critical={} warning={} info={}]".format(
            report.base_count,
            report.new_count,
            report.total_changes(),
            counts["critical"],
            counts["warning"],
            counts["info"],
        )
    )
    if not report.changes:
        lines.append("  No changes detected.")
        return "\n".join(lines)

    lines.append("-" * 72)
    for c in report.changes:
        tag = _SEV_TAG.get(c.severity, "[?]")
        title = (c.title[:40] + "...") if len(c.title) > 43 else c.title
        lines.append("{} {:<11} {}".format(tag, c.nct_id, c.message))
        if title:
            lines.append("            {}".format(title))
    lines.append("-" * 72)
    threshold = SEVERITY_ORDER.get(fail_on, 1)
    flagged = sum(
        1 for c in report.changes if SEVERITY_ORDER.get(c.severity, 0) >= threshold
    )
    lines.append(
        "{} finding(s) at/above '{}' severity.".format(flagged, fail_on)
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Diff and monitor clinical-trial records, alerting on "
        "status / enrollment / phase changes. CI-schedulable.",
        epilog="Example: trialwatch diff old.json new.json --format json "
        "--fail-on warning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version",
        version="{} {}".format(TOOL_NAME, TOOL_VERSION),
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    diff_p = sub.add_parser(
        "diff",
        help="diff two trial snapshots and report changes",
        description="Compare an old (baseline) snapshot against a new snapshot "
        "and report status / enrollment / phase / sponsor / completion "
        "changes plus added / removed trials.",
    )
    diff_p.add_argument("old", help="baseline snapshot JSON file")
    diff_p.add_argument("new", help="new snapshot JSON file")
    diff_p.add_argument(
        "--enrollment-threshold", type=float, default=20.0, metavar="PCT",
        help="enrollment swing %% that escalates info->warning (default: 20)",
    )
    diff_p.add_argument(
        "--fail-on", choices=["critical", "warning", "info"], default="warning",
        help="minimum severity that causes a non-zero exit (default: warning)",
    )
    diff_p.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="output format (default: table)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "diff":
        if args.enrollment_threshold < 0:
            print(
                "error: --enrollment-threshold must be >= 0, got {!r}".format(
                    args.enrollment_threshold
                ),
                file=sys.stderr,
            )
            return 2

        try:
            base = load_trials(args.old)
            new = load_trials(args.new)
        except FileNotFoundError as exc:
            print("error: file not found: {}".format(exc.filename), file=sys.stderr)
            return 2
        except PermissionError as exc:
            print("error: {}".format(exc), file=sys.stderr)
            return 2
        except (ValueError, json.JSONDecodeError) as exc:
            print("error: {}".format(exc), file=sys.stderr)
            return 2
        except OSError as exc:
            print("error: cannot read file: {}".format(exc), file=sys.stderr)
            return 2

        try:
            report = diff_trials(
                base, new, enrollment_pct_threshold=args.enrollment_threshold
            )
        except (ValueError, TypeError) as exc:
            print("error: {}".format(exc), file=sys.stderr)
            return 2

        if args.format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(_render_table(report, args.fail_on))

        return 1 if report.has_findings(args.fail_on) else 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
