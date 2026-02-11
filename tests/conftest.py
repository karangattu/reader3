"""Test configuration to isolate test data from the real library.

This ensures test runs do not write collections, tags, or other user data
into the real books directory.
"""

import os
import shutil
import tempfile

import pytest

# Create a dedicated temp books directory before any tests import server
TEST_BOOKS_DIR = tempfile.mkdtemp(prefix="reader3-tests-")
os.environ["READER3_BOOKS_DIR"] = TEST_BOOKS_DIR

# Import server after setting the env var so it binds to the temp dir
import server  # noqa: E402

# Rebind globals to the temp dir and clear caches
server.BOOKS_DIR = TEST_BOOKS_DIR
server.user_data_manager = server.UserDataManager(server.BOOKS_DIR)
server.load_book_cached.cache_clear()
server.get_cached_reading_times.cache_clear()
server.load_book_metadata.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def cleanup_books_dir():
    """Flush and remove the temp books directory after the test session."""
    yield
    try:
        server.user_data_manager.flush()
    except Exception:
        pass
    shutil.rmtree(TEST_BOOKS_DIR, ignore_errors=True)
