from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock


def stub_if_missing(name: str) -> None:
    if name in sys.modules:
        return
    try:
        importlib.import_module(name)
    except ImportError:
        sys.modules[name] = MagicMock()
