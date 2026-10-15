"""Shared test setup.

pytest imports this file before any test module, so the environment set here
is in place before tests import app code. Tests talk to the real FalkorDB
(rule 1: no in-memory fallback); if it is down, the whole session is skipped
with a clear message instead of failing with connection errors.
"""

import os

import pytest

from app.config import settings

os.environ.setdefault("FALKORDB_HOST", settings.falkordb_host)
os.environ.setdefault("FALKORDB_PORT", str(settings.falkordb_port))

from app.graph.client import ping  # noqa: E402  (after the environment is set)


@pytest.fixture(scope="session", autouse=True)
def require_falkordb():
    if not ping():
        pytest.skip("FalkorDB is not reachable - run docker compose up -d")
