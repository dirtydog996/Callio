#!/usr/bin/env python3
"""Collect voice latency baseline JSON from repeated e2e WebSocket rounds."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from callio.config.latency_budget import summarize_turn_metrics

_spec = importlib.util.spec_from_file_location(
    "e2e_voice_test",
    ROOT / "scripts" / "e2e-voice-test.py",
)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_module)
run_voice_rounds = _module.run_voice_rounds


async def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Callio voice latency baseline")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--out", default="latency_baseline.json")
    args = parser.parse_args()

    results = await run_voice_rounds(args.base_url, rounds=args.rounds)
    turns = [r.get("latency") for r in results if r.get("latency")]
    output = {
        "rounds_requested": args.rounds,
        "rounds_with_latency": len(turns),
        "turns": turns,
        "summary": summarize_turn_metrics(turns),
    }
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(turns)} turns)")
    return 0 if turns else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
