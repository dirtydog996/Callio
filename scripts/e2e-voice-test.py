#!/usr/bin/env python3
"""End-to-end smoke test for Callio voice WebSocket pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 16000
CHUNK_SAMPLES = 3200  # 200ms @ 16kHz


def _generate_test_pcm_linux(duration_sec: float = 1.6, freq: float = 440.0) -> bytes:
    samples = int(SAMPLE_RATE * duration_sec)
    pcm = bytearray()
    for i in range(samples):
        # Mild AM to mimic speech envelope
        env = 0.35 + 0.25 * math.sin(2 * math.pi * 3.5 * i / SAMPLE_RATE)
        value = int(32767 * env * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        pcm.extend(struct.pack("<h", value))
    return bytes(pcm)


def _generate_test_pcm(text: str = "hello") -> bytes:
    if shutil.which("say") and shutil.which("afconvert"):
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "test.aiff"
            wav = Path(tmp) / "test.wav"
            subprocess.run(["say", "-o", str(aiff), text], check=True, capture_output=True)
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", f"LEI16@{SAMPLE_RATE}", str(aiff), str(wav)],
                check=True,
                capture_output=True,
            )
            with wave.open(str(wav), "rb") as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != SAMPLE_RATE:
                    raise RuntimeError("unexpected wav format from afconvert")
                return wf.readframes(wf.getnframes())
    return _generate_test_pcm_linux()


def _http_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode())


async def _check_health(base_url: str) -> dict:
    return _http_json(f"{base_url}/api/v1/health")


async def _run_voice_round(
    ws_url: str,
    *,
    resume_session_id: str | None = None,
    utterance: str = "hello",
    timeout_sec: float = 120.0,
) -> dict:
    if resume_session_id:
        sep = "&" if "?" in ws_url else "?"
        ws_url = f"{ws_url}{sep}resume_session_id={resume_session_id}"

    pcm = _generate_test_pcm(utterance)
    messages: list[dict] = []
    audio_chunks = 0
    session_id: str | None = None
    transcription: str | None = None
    assistant_text: str | None = None
    latency_payload: dict | None = None

    async with websockets.connect(ws_url, max_size=8 * 1024 * 1024) as ws:
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
            except asyncio.TimeoutError:
                break
            if isinstance(raw, bytes):
                audio_chunks += 1
                continue
            payload = json.loads(raw)
            messages.append(payload)
            if payload.get("type") == "session":
                session_id = payload.get("session_id")
                break

        if not session_id:
            raise RuntimeError(f"no session_id in opening messages: {messages}")

        silence = b"\x00\x00" * CHUNK_SAMPLES
        for offset in range(0, len(pcm), CHUNK_SAMPLES * 2):
            await ws.send(pcm[offset : offset + CHUNK_SAMPLES * 2])
            await asyncio.sleep(0.2)
        for _ in range(8):
            await ws.send(silence)
            await asyncio.sleep(0.2)

        end_at = time.monotonic() + timeout_sec
        while time.monotonic() < end_at:
            remaining = end_at - time.monotonic()
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                if transcription and assistant_text and latency_payload:
                    break
                continue
            if isinstance(raw, bytes):
                audio_chunks += 1
                continue
            payload = json.loads(raw)
            messages.append(payload)
            if payload.get("type") == "transcription" and payload.get("text"):
                transcription = payload["text"]
            if payload.get("type") == "assistant" and payload.get("text"):
                assistant_text = payload["text"]
            if payload.get("type") == "latency":
                latency_payload = {
                    "turn_id": payload.get("turn_id"),
                    "timestamps_ms": payload.get("timestamps_ms", {}),
                    "derived_ms": payload.get("derived_ms", {}),
                }

    return {
        "session_id": session_id,
        "transcription": transcription,
        "assistant_text": assistant_text,
        "audio_chunks": audio_chunks,
        "latency": latency_payload,
        "messages": messages,
    }


async def run_voice_rounds(base_url: str, *, rounds: int = 1, utterance: str = "hello") -> list[dict]:
    base = base_url.rstrip("/")
    ws_scheme = "wss" if base.startswith("https") else "ws"
    ws_url = f"{ws_scheme}://{base.split('://', 1)[1]}/ws"
    results: list[dict] = []
    for i in range(rounds):
        result = await _run_voice_round(ws_url, utterance=f"{utterance} {i + 1}")
        results.append(result)
        await asyncio.sleep(0.5)
    return results


async def main() -> int:
    parser = argparse.ArgumentParser(description="Callio voice E2E smoke test")
    parser.add_argument("--base-url", default=os.getenv("CALLIO_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--utterance", default="hello")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--resume-session-id", default="")
    parser.add_argument("--two-round-resume", action="store_true", help="run round1 then resume round2")
    parser.add_argument("--latency-budget", action="store_true", help="check latency budget from WS events")
    parser.add_argument("--baseline-out", default="", help="write latency baseline JSON path")
    parser.add_argument("--rounds", type=int, default=1, help="number of voice rounds (latency mode)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    ws_scheme = "wss" if base.startswith("https") else "ws"
    ws_url = f"{ws_scheme}://{base.split('://', 1)[1]}/ws"

    print(f"[1/3] health check {base}/api/v1/health")
    health = await _check_health(base)
    print("      ", json.dumps(health, ensure_ascii=False))

    if not health.get("whisper_ready"):
        print("FAIL: whisper not ready:", health.get("whisper_error"))
        return 1

    rounds = args.rounds if args.latency_budget or args.baseline_out else 1
    print(f"[2/3] voice round(s) via {ws_url} (n={rounds})")
    results = await run_voice_rounds(base, rounds=rounds, utterance=args.utterance)
    result = results[-1]
    print("      session_id:", result["session_id"])
    print("      transcription:", result["transcription"])
    print("      assistant:", result["assistant_text"])
    print("      downlink audio chunks:", result["audio_chunks"])
    if result.get("latency"):
        print("      latency:", json.dumps(result["latency"], ensure_ascii=False))

    if args.two_round_resume and result["session_id"]:
        print("[2b/3] resume round")
        await asyncio.sleep(1)
        resume_result = await _run_voice_round(
            ws_url,
            resume_session_id=result["session_id"],
            utterance="continue",
            timeout_sec=args.timeout,
        )
        print("      resumed session:", resume_result["session_id"])
        print("      same session:", resume_result["session_id"] == result["session_id"])
        if resume_result["session_id"] != result["session_id"]:
            print("FAIL: resume did not reuse session_id")
            return 1
        result = resume_result

    if args.baseline_out or args.latency_budget:
        sys.path.insert(0, str(ROOT))
        from callio.config.latency_budget import check_budget, summarize_turn_metrics

        turns = [r["latency"] for r in results if r.get("latency")]
        summary = summarize_turn_metrics(turns)
        baseline = {
            "rounds_requested": rounds,
            "rounds_with_latency": len(turns),
            "turns": turns,
            "summary": summary,
        }
        if args.baseline_out:
            Path(args.baseline_out).write_text(
                json.dumps(baseline, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Wrote baseline: {args.baseline_out}")
        if args.latency_budget:
            passed, checks = check_budget(summary)
            print("Latency budget:")
            for row in checks:
                print(
                    f"  {row['stage']}: median={row['median_ms']} (<= {row['median_budget_ms']}), "
                    f"p90={row['p90_ms']} (<= {row['p90_budget_ms']}) -> {'PASS' if row['pass'] else 'FAIL'}"
                )
            if not passed:
                print("FAIL: latency budget exceeded")
                return 1

    print("[3/3] session persisted?")
    sessions = _http_json(f"{base}/api/v1/sessions").get("items", [])
    found = next((s for s in sessions if s.get("session_id") == result["session_id"]), None)
    print("      in session list:", bool(found))

    ok = bool(result["session_id"]) and (result["transcription"] or result["assistant_text"])
    if ok:
        print("PASS: voice pipeline responded")
        return 0
    print("FAIL: no transcription or assistant response")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
