"""TRIALWATCH MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from trialwatch.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-trialwatch[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-trialwatch[mcp]'")
        return 1
    app = FastMCP("trialwatch")

    @app.tool()
    def trialwatch_scan(target: str) -> str:
        """Query, diff, and monitor ClinicalTrials.gov records, alerting on status, enrollment, or result changes.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
