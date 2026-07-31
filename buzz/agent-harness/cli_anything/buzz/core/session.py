from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


NATIVE_DEFAULT_RELAY = "http://localhost:3000"
NATIVE_DEFAULT_FORMAT = "json"
SESSION_HISTORY_LIMIT = 100


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
        history = _validate_snapshots(data.get("history"), "history")
        future = _validate_snapshots(data.get("future"), "future")
        return cls(
            relay_url=relay_url,
            output_format=output_format,
            history=history[-SESSION_HISTORY_LIMIT:],
            future=future[-SESSION_HISTORY_LIMIT:],
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
        with _session_lock(self.path, exclusive=False):
            return _load_unlocked(self.path)

    def save(self, state: SessionState) -> Path:
        with _session_lock(self.path, exclusive=True):
            _save_unlocked(self.path, state)
        return self.path

    def mutate(
        self,
        state: SessionState,
        *,
        relay_url: str | None | object = ...,
        output_format: str | object = ...,
        persist: bool = False,
    ) -> SessionState:
        if persist:
            return self._transaction(
                state,
                lambda current: self.mutate(
                    current,
                    relay_url=relay_url,
                    output_format=output_format,
                ),
            )
        state.history.append(state.snapshot())
        state.history[:] = state.history[-SESSION_HISTORY_LIMIT:]
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

    def reset(self, state: SessionState, *, persist: bool = False) -> SessionState:
        return self.mutate(
            state,
            relay_url=None,
            output_format=NATIVE_DEFAULT_FORMAT,
            persist=persist,
        )

    def undo(self, state: SessionState, *, persist: bool = False) -> dict[str, Any]:
        if persist:
            self._transaction(state, lambda current: self.undo(current))
            return state.snapshot()
        if not state.history:
            raise ValueError("No local Buzz session change to undo")
        current = state.snapshot()
        previous = state.history.pop()
        state.future.append(current)
        state.future[:] = state.future[-SESSION_HISTORY_LIMIT:]
        state.restore(previous)
        return state.snapshot()

    def redo(self, state: SessionState, *, persist: bool = False) -> dict[str, Any]:
        if persist:
            self._transaction(state, lambda current: self.redo(current))
            return state.snapshot()
        if not state.future:
            raise ValueError("No local Buzz session change to redo")
        current = state.snapshot()
        following = state.future.pop()
        state.history.append(current)
        state.history[:] = state.history[-SESSION_HISTORY_LIMIT:]
        state.restore(following)
        return state.snapshot()

    def _transaction(self, state: SessionState, operation: Any) -> SessionState:
        with _session_lock(self.path, exclusive=True):
            current = _load_unlocked(self.path)
            operation(current)
            _save_unlocked(self.path, current)
        state.relay_url = current.relay_url
        state.output_format = current.output_format
        state.history = current.history
        state.future = current.future
        return state


def _validate_snapshots(value: Any, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Buzz session {field_name} must be a JSON array")
    snapshots: list[dict[str, Any]] = []
    for index, snapshot in enumerate(value):
        if not isinstance(snapshot, dict):
            raise ValueError(
                f"Buzz session {field_name}[{index}] must be a JSON object"
            )
        validated = SessionState()
        validated.restore(snapshot)
        snapshots.append(validated.snapshot())
    return snapshots


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


@contextmanager
def _session_lock(path: Path, *, exclusive: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        locked = False
        try:
            import fcntl

            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(handle.fileno(), mode)
            locked = True
        except (ImportError, OSError):
            pass
        try:
            yield
        finally:
            if locked:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_unlocked(path: Path) -> SessionState:
    if not path.exists():
        return SessionState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed Buzz session JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Buzz session file is not a JSON object: {path}")
    return SessionState.from_dict(data)


def _save_unlocked(path: Path, state: SessionState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
