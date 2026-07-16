from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Sequence


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def build_url(base_url: str, path: str) -> str:
    return f"{normalize_base_url(base_url)}{path if path.startswith('/') else f'/{path}'}"


def build_dispatch_payload(
    title: str,
    description: str,
    *,
    session_id: str | None = None,
    difficulty_level: int = 1,
) -> dict[str, Any]:
    clean_description = description.strip()
    clean_title = title.strip() or (clean_description[:24] + ("…" if len(clean_description) > 24 else "")) or "manual-task"
    return {
        "session_id": session_id,
        "feature_name": clean_title,
        "description": clean_description,
        "difficulty_level": difficulty_level,
    }


def request_json(base_url: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(build_url(base_url, path), data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failure path
        body = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network failure path
        raise SystemExit(f"Connection failed: {exc.reason}") from exc


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Callio CLI client")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Callio server base URL")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="Show server health")
    subparsers.add_parser("sessions", help="List sessions")

    tasks_parser = subparsers.add_parser("tasks", help="List tasks")
    tasks_parser.add_argument("--session-id", help="Optional session filter")

    dispatch_parser = subparsers.add_parser("dispatch", help="Dispatch a background task")
    dispatch_parser.add_argument("--title", default="", help="Task title")
    dispatch_parser.add_argument("--description", required=True, help="Task description")
    dispatch_parser.add_argument("--session-id", help="Optional session ID")
    dispatch_parser.add_argument("--difficulty", type=int, default=1, help="Difficulty level")

    confirm_parser = subparsers.add_parser("confirm-all", help="Confirm all proposed tasks in a session")
    confirm_parser.add_argument("session_id", help="Session ID")

    cancel_parser = subparsers.add_parser("cancel-running", help="Cancel a running task")
    cancel_parser.add_argument("node_id", help="Task node ID")
    return parser


def run_command(args: argparse.Namespace) -> Any:
    base_url = normalize_base_url(args.base_url)
    if args.command == "health":
        return request_json(base_url, "/api/v1/health")
    if args.command == "sessions":
        return request_json(base_url, "/api/v1/sessions")
    if args.command == "tasks":
        if args.session_id:
            return request_json(base_url, f"/api/v1/sessions/{args.session_id}/tasks")
        return request_json(base_url, "/api/v1/tasks")
    if args.command == "dispatch":
        payload = build_dispatch_payload(
            args.title,
            args.description,
            session_id=args.session_id,
            difficulty_level=args.difficulty,
        )
        return request_json(base_url, "/api/v1/tasks/dispatch", method="POST", payload=payload)
    if args.command == "confirm-all":
        return request_json(
            base_url,
            f"/api/v1/sessions/{args.session_id}/tasks/confirm",
            method="POST",
            payload={"node_ids": [], "confirm_all": True},
        )
    if args.command == "cancel-running":
        return request_json(base_url, f"/api/v1/tasks/{args.node_id}/cancel", method="POST")
    raise SystemExit(f"Unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = run_command(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
