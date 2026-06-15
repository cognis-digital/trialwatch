"""TRIALWATCH MCP server — exposes diff_trials() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
import json
import sys


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-trialwatch[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-trialwatch[mcp]'")
        return 1

    try:
        from trialwatch.core import load_trials, diff_trials
    except ImportError as exc:
        print("error: trialwatch core unavailable: {}".format(exc), file=sys.stderr)
        return 1

    app = FastMCP("trialwatch")

    @app.tool()
    def trialwatch_diff(old_path: str, new_path: str) -> str:
        """Diff two ClinicalTrials.gov snapshot JSON files and return JSON findings.

        Parameters
        ----------
        old_path: path to the baseline snapshot JSON file
        new_path: path to the new snapshot JSON file
        """
        try:
            base = load_trials(old_path)
            new = load_trials(new_path)
            report = diff_trials(base, new)
            return json.dumps(report.to_dict(), indent=2)
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            return json.dumps({"error": str(exc)})

    app.run()
    return 0
