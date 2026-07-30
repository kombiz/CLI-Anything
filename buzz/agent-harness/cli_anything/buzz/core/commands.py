from __future__ import annotations

import json
from typing import Any, Iterable, Sequence


NATIVE_GROUPS = (
    "agents",
    "messages",
    "channels",
    "canvas",
    "reactions",
    "emoji",
    "dms",
    "users",
    "workflows",
    "feed",
    "social",
    "notes",
    "repos",
    "patches",
    "issues",
    "pr",
    "media",
    "upload",
    "mem",
    "pack",
    "moderation",
)

GROUP_HELP = {
    "agents": "Plan or approve Desktop-managed agents and send owner-reviewed drafts.",
    "messages": "Send, read, search, and manage messages.",
    "channels": "Create, configure, and manage channels.",
    "canvas": "Get and set channel canvas documents.",
    "reactions": "Add, remove, and list message reactions.",
    "emoji": "Manage custom emoji.",
    "dms": "List, open, and manage direct messages.",
    "users": "Look up users and manage profiles or presence.",
    "workflows": "Create, trigger, and manage workflows.",
    "feed": "Read the activity feed.",
    "social": "Publish notes and manage the social graph.",
    "notes": "Publish and edit long-form knowledge notes.",
    "repos": "Announce and discover git repositories.",
    "patches": "Send and manage git patches.",
    "issues": "Create and manage git issues.",
    "pr": "Open and manage git pull requests.",
    "media": "Upload and download Blossom media.",
    "upload": "Upload files to the Blossom store.",
    "mem": "Manage persistent agent engrams.",
    "pack": "Validate and inspect local persona packs.",
    "moderation": "Manage community moderation.",
}

SECRET_FLAGS = ("--private-key", "--auth-tag")


def ensure_no_secret_args(args: Sequence[str]) -> None:
    for token in args:
        if any(token == flag or token.startswith(f"{flag}=") for flag in SECRET_FLAGS):
            raise ValueError(
                f"{token.split('=', 1)[0]} is blocked by CLI-Anything Buzz; "
                "use BUZZ_PRIVATE_KEY or BUZZ_AUTH_TAG in the environment"
            )


def redact_args(args: Iterable[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for token in args:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        matching = next((flag for flag in SECRET_FLAGS if token == flag), None)
        if matching:
            redacted.append(token)
            hide_next = True
            continue
        matching = next(
            (flag for flag in SECRET_FLAGS if token.startswith(f"{flag}=")),
            None,
        )
        if matching:
            redacted.append(f"{matching}=<redacted>")
            continue
        redacted.append(token)
    return redacted


def build_native_args(
    group: str,
    args: Sequence[str],
    *,
    relay_url: str | None,
    output_format: str,
) -> list[str]:
    if not group:
        raise ValueError("A native Buzz command group is required")
    ensure_no_secret_args((group, *args))
    native_args: list[str] = []
    if relay_url:
        native_args.extend(["--relay", relay_url])
    native_args.extend(["--format", output_format, group])
    native_args.extend(args)
    return native_args


def parse_stdout(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse_stderr(stderr: str) -> Any:
    text = stderr.strip()
    if not text:
        return None
    for line in reversed(text.splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return text


def result_payload(
    executable: str,
    native_args: Sequence[str],
    *,
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": returncode == 0,
        "backend": "buzz",
        "command": redact_args((executable, *native_args)),
        "exit_code": returncode,
    }
    if returncode == 0:
        payload["data"] = parse_stdout(stdout)
        if stderr.strip():
            payload["stderr"] = stderr.strip()
    else:
        payload["error"] = parse_stderr(stderr)
        if stdout.strip():
            payload["data"] = parse_stdout(stdout)
    return payload


def dry_run_payload(executable: str, native_args: Sequence[str]) -> dict[str, Any]:
    return {
        "ok": True,
        "backend": "buzz",
        "executed": False,
        "dry_run": True,
        "command": redact_args((executable, *native_args)),
    }
