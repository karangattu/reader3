"""Compatibility shim for Reader3 search services."""

from __future__ import annotations

import sys

from reader3.services import search as _search_module
from reader3.services.search import *  # noqa: F401,F403,E402

sys.modules[__name__] = _search_module
