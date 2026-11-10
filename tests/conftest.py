"""Pytest configuration: avoid breaking real package imports during collection."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from unittest.mock import MagicMock


def _restore_submodule(parent: str, child: str) -> None:
    full = f"{parent}.{child}"
    parent_mod = sys.modules.get(parent)
    if parent_mod is None or isinstance(parent_mod, MagicMock):
        return
    if full in sys.modules and not isinstance(sys.modules[full], MagicMock):
        return
    try:
        sys.modules[full] = importlib.import_module(full)
    except Exception:
        pass


def pytest_ignore_collect(collection_path, config) -> bool:
    """Do not import isolated voice-pipeline stubs during the default test run."""
    if collection_path.name != "test_voice_pipeline.py":
        return False
    markexpr = (config.option.markexpr or "").strip()
    if markexpr in ("", "not isolated"):
        return True
    if "isolated" in markexpr and "not isolated" not in markexpr:
        return False
    return True


def pytest_configure(config) -> None:
    """If a prior test module left callio.voice as a MagicMock, restore the real package."""
    voice = sys.modules.get("callio.voice")
    if isinstance(voice, MagicMock):
        sys.modules.pop("callio.voice", None)
        for key in list(sys.modules):
            if key.startswith("callio.voice."):
                sys.modules.pop(key, None)
        importlib.import_module("callio.voice")
    elif isinstance(voice, ModuleType) and voice.__spec__ is None:
        importlib.import_module("callio.voice")


def _pipecat_looks_stubbed() -> bool:
    silero = sys.modules.get("pipecat.audio.vad.silero")
    if silero is None:
        return False
    if isinstance(silero, MagicMock):
        return True
    spec = getattr(silero, "__spec__", None)
    if spec is None and getattr(silero, "__file__", None) is None:
        return True
    try:
        importlib.import_module("pipecat.audio.vad.data")
    except ModuleNotFoundError:
        return True
    return False


def _restore_pipecat() -> None:
    for key in list(sys.modules):
        if key == "pipecat" or key.startswith("pipecat."):
            sys.modules.pop(key, None)
    importlib.import_module("pipecat")


def pytest_runtest_setup(item) -> None:
    """Before each test, restore pipecat if an earlier stub replaced it with fakes."""
    pipecat = sys.modules.get("pipecat")
    if isinstance(pipecat, MagicMock) or _pipecat_looks_stubbed():
        _restore_pipecat()
