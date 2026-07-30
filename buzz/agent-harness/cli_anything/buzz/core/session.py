from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


NATIVE_DEFAULT_RELAY = "http://localhost:3000"
NATIVE_DEFAULT_FORMAT = "json"


def default_session_path() -> Path:
    configured = os.environ.get("CLI_ANYTHING_BUZZ_SESSION")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cli-anything-buzz" / "session.json"


@dataclass
class SessionState:
    relay_url: str | None = None
    output_format: str = NATIVE_DEFAULT_FORMAT
    history: list[dict[str, Any]] = field(default_factory=list)
    future: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relay_url": self.relay_url,
            "output_format": self.output_format,
            "history": self.history,
            "future": self.future,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        output_format = str(data.get("output_format") or NATIVE_DEFAULT_FORMAT)
        if output_format not in {"json", "compact"}:
            raise ValueError(f"Unsupported Buzz output format: {output_format}")
        relay_url = data.get("relay_url")
        if relay_url is not None:
            relay_url = validate_relay_url(str(relay_url))
        return cls(
            relay_url=relay_url,
            output_format=output_format,
            history=list(data.get("history") or []),
            future=list(data.get("future") or []),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "relay_url": self.relay_url,
            "output_format": self.output_format,
        }

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        relay_url = snapshot.get("relay_url")
        self.relay_url = (
            validate_relay_url(str(relay_url)) if relay_url is not None else None
        )
        output_format = str(snapshot.get("output_format") or NATIVE_DEFAULT_FORMAT)
        if output_format not in {"json", "compact"}:
            raise ValueError(f"Unsupported Buzz output format: {output_format}")
        self.output_format = output_format


class SessionStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser() if path else default_session_path()

    def load(self) -> SessionState:
        if not self.path.exists():
            return SessionState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed Buzz session JSON: {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Buzz session file is not a JSON object: {self.path}")
        return SessionState.from_dict(data)

    def save(self, state: SessionState) -> Path:
        _locked_save_json(self.path, state.to_dict(), indent=2, sort_keys=True)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        return self.path

    def mutate(
        self,
        state: SessionState,
        *,
        relay_url: str | None | object = ...,
        output_format: str | object = ...,
    ) -> SessionState:
        state.history.append(state.snapshot())
        if relay_url is not ...:
            state.relay_url = (
                validate_relay_url(str(relay_url)) if relay_url is not None else None
            )
        if output_format is not ...:
            value = str(output_format)
            if value not in {"json", "compact"}:
                raise ValueError(f"Unsupported Buzz output format: {value}")
            state.output_format = value
        state.future.clear()
        return state

    def reset(self, state: SessionState) -> SessionState:
        return self.mutate(
            state,
            relay_url=None,
            output_format=NATIVE_DEFAULT_FORMAT,
        )

    def undo(self, state: SessionState) -> dict[str, Any]:
        if not state.history:
            raise ValueError("No local Buzz session change to undo")
        current = state.snapshot()
        previous = state.history.pop()
        state.future.append(current)
        state.restore(previous)
        return state.snapshot()

    def redo(self, state: SessionState) -> dict[str, Any]:
        if not state.future:
            raise ValueError("No local Buzz session change to redo")
        current = state.snapshot()
        following = state.future.pop()
        state.history.append(current)
        state.restore(following)
        return state.snapshot()


def validate_relay_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Relay URL must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("Relay URL must not contain embedded credentials")
    return candidate


def resolve_settings(
    requested_relay: str | None,
    requested_format: str | None,
    state: SessionState,
    environ: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    env = os.environ if environ is None else environ
    relay = requested_relay or state.relay_url or env.get("BUZZ_RELAY_URL") or None
    if relay:
        relay = validate_relay_url(relay)
    output_format = requested_format or state.output_format or NATIVE_DEFAULT_FORMAT
    if output_format not in {"json", "compact"}:
        raise ValueError(f"Unsupported Buzz output format: {output_format}")
    return relay, output_format


def _locked_save_json(path: Path, data: dict[str, Any], **dump_kwargs: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("r+", encoding="utf-8")
    except FileNotFoundError:
        handle = path.open("w+", encoding="utf-8")
    with handle:
        locked = False
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            locked = True
        except (ImportError, OSError):
            pass
        try:
            handle.seek(0)
            handle.truncate()
            json.dump(data, handle, **dump_kwargs)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            if locked:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
