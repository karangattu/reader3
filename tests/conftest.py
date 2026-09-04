"""Test configuration to isolate test data from the real library.

This ensures test runs do not write collections, tags, or other user data
into the real books directory.
"""

import os
import shutil
import sys
import tempfile

import pytest

# Create a dedicated temp books directory before any tests import server
TEST_BOOKS_DIR = tempfile.mkdtemp(prefix="reader3-tests-")
os.environ["READER3_BOOKS_DIR"] = TEST_BOOKS_DIR

# Import server after setting the env var so it binds to the temp dir
import server  # noqa: E402

# The canonical state now lives in reader3.api.deps — update it there too
from reader3.api import deps as _deps  # noqa: E402
from reader3.storage.user_data import UserDataManager  # noqa: E402

# Rebind globals on both the shim module and the deps module
server.BOOKS_DIR = TEST_BOOKS_DIR
_deps.BOOKS_DIR = TEST_BOOKS_DIR

_new_udm = UserDataManager(TEST_BOOKS_DIR)
server.user_data_manager = _new_udm
_deps.user_data_manager = _new_udm

for route_mod in ("progress", "preferences", "annotations", "library", "reader", "pdf"):
    mod = sys.modules.get(f"reader3.api.routes.{route_mod}")
    if mod and hasattr(mod, "user_data_manager"):
        setattr(mod, "user_data_manager", _new_udm)

# Clear caches (they live on the deps functions)
_deps.load_book_cached.cache_clear()
_deps.get_cached_reading_times.cache_clear()
_deps.load_book_metadata.cache_clear()

# Keep backward compat aliases on server module
server.load_book_cached = _deps.load_book_cached
server.get_cached_reading_times = _deps.get_cached_reading_times
server.load_book_metadata = _deps.load_book_metadata


@pytest.fixture(scope="session", autouse=True)
def cleanup_books_dir():
    """Flush and remove the temp books directory after the test session."""
    yield
    try:
        _deps.user_data_manager.flush()
    except Exception:
        pass
    shutil.rmtree(TEST_BOOKS_DIR, ignore_errors=True)
