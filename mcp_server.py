"""Grounding fatigue-monitor MCP server.
Run: uv run --project /path/to/grounding /path/to/grounding/mcp_server.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mcp.server.fastmcp import FastMCP

import agents, report
import grounding as g

mcp = FastMCP("grounding")


@mcp.tool()
def get_fatigue() -> dict:
    """Minutes of continuous screen time since the user's last real break, and whether they should step away."""
    return g.status()


@mcp.tool()
def get_offline_mission() -> str:
    """Generate a specific offline mission (15-30 min, ends with a photo) for the user. Turns the lamp green."""
    return agents.run_mission(force=True)["mission"]


@mcp.tool()
def journal_photo(path: str) -> str:
    """Turn a photo the user took outside into a reflective journal entry (local vision model)."""
    p = Path(path).expanduser()
    return agents.run_reflect(p.read_bytes(), p.name)["entry"]


@mcp.tool()
def set_lamp(state: str) -> str:
    """Set the desk lamp: 'break' (green, step away) or 'focus' (warm)."""
    if state not in g.COLORS:
        return "state must be 'break' or 'focus'"
    return g.lamp(state)


@mcp.tool()
def weekly_report(days: int = 7) -> str:
    """Build a printable PDF of the user's offline achievements; returns its path."""
    return str(report.build(days))


if __name__ == "__main__":
    mcp.run()
