"""Compatibility shim for Reader3 user-state storage."""

from __future__ import annotations

import sys

from reader3.storage import user_data as _storage_module
from reader3.storage.user_data import *  # noqa: F401,F403,E402

sys.modules[__name__] = _storage_module
