from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from urllib.request import urlopen


INSTALL_HELP = """Buzz's native CLI is not installed.

Build it from the Buzz source:
  git clone https://github.com/block/buzz.git
  cd buzz
  cargo install --path crates/buzz-cli
"""
DEFAULT_BUZZ_TIMEOUT = 60.0
BUZZ_TIMEOUT_ENV = "CLI_ANYTHING_BUZZ_TIMEOUT"


@dataclass(frozen=True)
class BackendResult:
    executable: str
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def find_buzz(
    explicit: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    requested = explicit or env.get("CLI_ANYTHING_BUZZ_BINARY")
    if requested:
        candidate = Path(requested).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
        raise RuntimeError(
            f"Buzz executable is not usable: {candidate}\n\n{INSTALL_HELP}"
        )
    discovered = shutil.which("buzz")
    if discovered:
        return str(Path(discovered).resolve())
    raise RuntimeError(INSTALL_HELP)


def run_buzz(
    args: Sequence[str],
    *,
    executable: str | None = None,
    input_text: str | None = None,
    timeout: float | None = None,
    environ: Mapping[str, str] | None = None,
) -> BackendResult:
    binary = find_buzz(executable, environ=environ)
    if timeout is None:
        env = os.environ if environ is None else environ
        configured = env.get(BUZZ_TIMEOUT_ENV)
        if configured:
            try:
                timeout = float(configured)
            except ValueError as exc:
                raise RuntimeError(f"{BUZZ_TIMEOUT_ENV} must be a number") from exc
            if timeout <= 0:
                raise RuntimeError(f"{BUZZ_TIMEOUT_ENV} must be greater than zero")
        else:
            timeout = DEFAULT_BUZZ_TIMEOUT
    completed = subprocess.run(
        [binary, *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(os.environ if environ is None else environ),
        check=False,
    )
    return BackendResult(
        executable=binary,
        args=tuple(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def parse_root_commands(help_text: str) -> list[str]:
    commands: list[str] = []
    in_commands = False
    for line in help_text.splitlines():
        if line.strip() == "Commands:":
            in_commands = True
            continue
        if in_commands and line.strip() == "Options:":
            break
        if not in_commands:
            continue
        match = re.match(r"^\s{2}([a-z][a-z0-9-]*)\s{2,}", line)
        if match and match.group(1) != "help":
            commands.append(match.group(1))
    return commands


def native_command_inventory(
    executable: str | None = None,
    *,
    timeout: float | None = None,
) -> tuple[str, list[str]]:
    result = run_buzz(["--help"], executable=executable, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "buzz --help failed")
    return result.executable, parse_root_commands(result.stdout)


def check_relay_liveness(relay_url: str, timeout: float = 3) -> dict[str, object]:
    url = relay_url.rstrip("/") + "/_liveness"
    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read(512).decode("utf-8", errors="replace").strip()
            return {
                "reachable": 200 <= response.status < 300,
                "status": response.status,
                "url": url,
                "body": body,
            }
    except Exception as exc:
        return {
            "reachable": False,
            "url": url,
            "error": str(exc),
        }
