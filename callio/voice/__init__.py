from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from callio.config.settings import Settings


def register_voice_routes(app: FastAPI, settings: Settings | None = None) -> None:
    from callio.voice.pipeline import register_voice_routes as _register

    _register(app, settings)


__all__ = ["register_voice_routes"]
