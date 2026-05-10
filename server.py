"""Compatibility shim for the packaged Reader3 FastAPI app."""

from __future__ import annotations

import sys

from reader3 import app as _app_module
from reader3.app import *  # noqa: F401,F403,E402

sys.modules[__name__] = _app_module

if __name__ == "__main__":
    _app_module.run()
