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


class UnknownWorkspace(LookupError):
    """A read asked for a workspace that has never been created."""



@cache
def get_db() -> FalkorDB:
    """Return the shared FalkorDB client (one connection pool per process)."""
    cloud_host = settings.falkordb_host
    cloud_password = settings.falkordb_password

    return FalkorDB(
        host=cloud_host,
        port=settings.falkordb_port,
        username=settings.falkordb_username or None,
        password=cloud_password or None,
        ssl=settings.falkordb_ssl,
        ssl_check_hostname=settings.falkordb_ssl,
        socket_connect_timeout=10,
    )



def graph_for(workspace: str, must_exist: bool = False) -> Graph:
    """Return the graph for a workspace, rejecting names outside ^[a-z0-9_]{1,32}$.

    With must_exist=True, raise UnknownWorkspace instead of returning a graph that does not exist yet.
    """
    if not isinstance(workspace, str) or not _WORKSPACE_RE.fullmatch(workspace):
        raise ValueError(f"invalid workspace name: {workspace!r} (allowed: ^[a-z0-9_]{{1,32}}$)")
    name = f"{GRAPH_PREFIX}{workspace}"
    # FalkorDB creates a graph on the first write query against it, so reads must check first.
    if must_exist and name not in get_db().list_graphs():
        raise UnknownWorkspace(f"workspace {workspace!r} does not exist; existing: {list_workspaces()}")
    return get_db().select_graph(name)


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
