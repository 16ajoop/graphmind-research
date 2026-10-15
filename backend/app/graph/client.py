"""FalkorDB connection and workspace -> graph mapping.

One workspace is one FalkorDB graph named "ws_<workspace>". Workspace names
are validated before they become part of a graph key, because a key cannot be
passed as a query parameter.
"""

import re
from functools import cache

from falkordb import FalkorDB, Graph

from app.config import settings

GRAPH_PREFIX = "ws_"
_WORKSPACE_RE = re.compile(r"^[a-z0-9_]{1,32}$")


@cache
def get_db() -> FalkorDB:
    """Return the shared FalkorDB client (one connection pool per process)."""
    return FalkorDB(
        host=settings.falkordb_host,
        port=settings.falkordb_port,
        socket_connect_timeout=2,
    )


def graph_for(workspace: str) -> Graph:
    """Return the graph for a workspace, rejecting names outside ^[a-z0-9_]{1,32}$."""
    if not isinstance(workspace, str) or not _WORKSPACE_RE.fullmatch(workspace):
        raise ValueError(f"invalid workspace name: {workspace!r} (allowed: ^[a-z0-9_]{{1,32}}$)")
    return get_db().select_graph(f"{GRAPH_PREFIX}{workspace}")


def list_workspaces() -> list[str]:
    """Return workspace names (graph names starting with "ws_", prefix removed)."""
    return sorted(
        name[len(GRAPH_PREFIX):]
        for name in get_db().list_graphs()
        if name.startswith(GRAPH_PREFIX)
    )


def ping() -> bool:
    """Return True if FalkorDB answers, False on any error. Never raises.

    Runs a read-only "RETURN 1" on an existing graph. A write-capable query on
    a missing graph would create an empty graph key, so when no graph exists
    yet, a successful GRAPH.LIST is taken as proof the server is up.
    """
    try:
        db = get_db()
        names = db.list_graphs()
        if names:
            db.select_graph(names[0]).ro_query("RETURN 1")
        return True
    except Exception:
        return False
