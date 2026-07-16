from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from callio.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)
_MAX_SNIPPET = 4000
_SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "__pycache__", ".callio_shadow"}


def collect_repo_context(description: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    root = Path(settings.sandbox_root).resolve()
    if not root.exists():
        return ""

    keywords = _keywords_from_description(description)
    snippets: list[str] = []

    if shutil.which("rg"):
        snippets.extend(_rgrep(root, keywords))
    snippets.extend(_scan_files(root, keywords))

    if not snippets:
        return f"Workspace: {root}\n(no matching code snippets found)"

    body = "\n\n---\n\n".join(snippets[:8])
    return f"Workspace: {root}\n\n{body[:_MAX_SNIPPET]}"


def _keywords_from_description(description: str) -> list[str]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", description)
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        low = token.lower()
        if low in seen or low in {"the", "and"}:
            continue
        seen.add(low)
        out.append(token)
        if len(out) >= 6:
            break
    return out or ["def", "class"]


def _rgrep(root: Path, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for kw in keywords[:4]:
        try:
            result = subprocess.run(
                ["rg", "-n", "--max-count", "3", "-g", "!.git/*", "-g", "!venv/*", kw, str(root)],
                capture_output=True, text=True, timeout=8,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        if result.stdout.strip():
            hits.append(f"## rg: {kw}\n{result.stdout.strip()[:800]}")
    return hits


def _scan_files(root: Path, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not any(kw.lower() in text.lower() for kw in keywords):
            continue
        rel = path.relative_to(root)
        hits.append(f"## {rel}\n{text[:600]}")
        if len(hits) >= 4:
            break
    return hits
