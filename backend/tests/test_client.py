"""Reads must never create graphs: a typo in a workspace name should fail loudly, not leave an empty graph."""
import pytest
from redis.exceptions import ResponseError

from app.graph.analysis import Analysis
from app.graph.client import UnknownWorkspace, get_db, graph_for

MISSING = "zz_missing_check"


@pytest.fixture(autouse=True)
def no_leftover_graph():
    """If an earlier failed run left the graph behind, remove it so each test starts clean."""
    def drop():
        if f"ws_{MISSING}" in get_db().list_graphs():
            get_db().select_graph(f"ws_{MISSING}").delete()
    drop()
    yield
    drop()


def test_unknown_workspace_raises_and_is_not_created():
    with pytest.raises(UnknownWorkspace):
        graph_for(MISSING, must_exist=True)
    assert f"ws_{MISSING}" not in get_db().list_graphs()


def test_analysis_reads_are_read_only():
    graph = get_db().select_graph(f"ws_{MISSING}")      # bypass the check on purpose
    with pytest.raises(ResponseError):                  # RO_QUERY on a missing graph errors instead of creating it
        Analysis(graph).run("library_papers")
    assert f"ws_{MISSING}" not in get_db().list_graphs()
